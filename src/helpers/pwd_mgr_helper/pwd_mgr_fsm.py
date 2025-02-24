import csv
from io import BytesIO

import aiofiles
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, BufferedInputFile
from cryptography.exceptions import InvalidTag

from config import db_manager, bot_cfg
from keyboards import InlineKeyboards
from models.db_record.password_record import EncryptedRecord, DecryptedRecord, PasswordRecord
from .pwd_mgr_crypto import PasswordManagerCryptoHelper as PwManUtils
from utils import BotUtils
from utils.storage_utils import StorageUtils
from models.callback_data import PasswordManagerCallbackData as PwManCbData
from .weak_pwd_exception import WeakPasswordException

MAX_CHAR_LIMIT: int = 64


class PasswordManagerFsmHelper(BotUtils):
    @staticmethod
    def is_master_password_valid(master_password: str) -> str:
        try:
            PwManUtils.validate_master_password(master_password)
        except WeakPasswordException as e:
            return str(e)
        return ""

    @staticmethod
    async def derive_key_from_master_password(master_password: str, message: Message) -> bytes:
        """derives a key, and verifies correctness."""
        salt: bytes = await db_manager.relational_db.get_salt(message.from_user.id)
        key: bytes = PwManUtils.derive_key(master_password, salt)
        rand_encrypted_record: EncryptedRecord = await db_manager.relational_db.get_rand_password(message.from_user.id)

        if rand_encrypted_record:
            try:
                PwManUtils.decrypt_record(encrypted_record=rand_encrypted_record, key=key)
            except InvalidTag:
                return b""
        return key

    @staticmethod
    async def show_service_logins(message: Message, state: FSMContext, key: bytes, service: str) -> None:
        pwd_offset: int = await StorageUtils.get_pm_pwd_offset(state)
        services_offset: int = await StorageUtils.get_pm_services_offset(state)
        encrypted_records: list[EncryptedRecord] = await db_manager.relational_db.get_passwords(
            user_id=message.from_user.id,
            service=service,
            offset=pwd_offset,
            limit=bot_cfg.dynamic_buttons_limit
        )
        decrypted_records: list[DecryptedRecord] = []
        for encrypted_record in encrypted_records:
            decrypted_record: DecryptedRecord = PwManUtils.decrypt_record(encrypted_record=encrypted_record, key=key)
            decrypted_records.append(decrypted_record)
        text: str = (
            f"*Service:* {service}\n"
            "Choose your login to see password"
        )
        await message.answer(
            text=text,
            reply_markup=InlineKeyboards.pwd_mgr_passwords(decrypted_records, service, pwd_offset, services_offset),
            parse_mode="Markdown"
        )

    @staticmethod
    def has_valid_input_length(login: str, password: str) -> bool:
        """Checks if the combined input length exceeds the max character limit."""
        return len(f"{PwManCbData.EnterPassword.__prefix__}{bot_cfg.sep}{login}{bot_cfg.sep}{password}") <= MAX_CHAR_LIMIT

    @staticmethod
    async def create_password_record(login: str, password: str, service: str, message: Message, key: bytes) -> None:
        encrypted_record = PwManUtils.encrypt_record(service=service, login=login, password=password, key=key)
        await db_manager.relational_db.create_password(
            user_id=message.from_user.id,
            service=encrypted_record.service,
            iv=encrypted_record.iv,
            tag=encrypted_record.tag,
            ciphertext=encrypted_record.ciphertext
        )

    @staticmethod
    async def split_user_input(user_input: str, maxsplit: int, sep: str = bot_cfg.sep) -> tuple:
        parts = tuple(user_input.split(sep=sep))
        return parts if len(parts) == maxsplit else tuple()

    @staticmethod
    async def resend_user_input_request(
            state: FSMContext,
            message: Message,
            error_message: str,
            current_state: str,
    ) -> None:
        await state.set_state(current_state)
        input_format: str = await StorageUtils.get_pm_input_format_text(state)
        message_to_delete: Message = await message.answer(
            text=f"{error_message}\n\n{input_format}",
            reply_markup=InlineKeyboards.return_to_services(offset=0)
        )
        await StorageUtils.set_message_id_to_delete(state, message_to_delete.message_id)

    @staticmethod
    async def handle_message_deletion(state: FSMContext, message: Message) -> str:
        current_state: str = await state.get_state()
        await state.set_state(None)
        await BotUtils.delete_fsm_message(state, message)
        await message.delete()
        return current_state

    @classmethod
    async def process_importing_from_file(cls, message: Message, key: bytes):
        temp_file_path = await cls.download_file(message)

        async with aiofiles.open(temp_file_path, "r") as f:
            content = await f.read()
            lines = content.splitlines()

        pwd_records: list[PasswordRecord] = []
        reader = csv.DictReader(lines)
        for row in reader:
            service = row.get("url", "").replace(bot_cfg.sep, "")
            if not service:
                continue
            login = row.get("username", "").replace(bot_cfg.sep, "")
            password = row.get("password", "").replace(bot_cfg.sep, "")
            encrypted_record = PwManUtils.encrypt_record(service=service, login=login, password=password, key=key)
            pwd_records.append(PasswordRecord(service=service, encrypted_record=encrypted_record))

        await db_manager.relational_db.import_passwords(user_id=message.from_user.id, pwd_records=pwd_records)
        await cls._delete_file(temp_file_path)

    @staticmethod
    async def process_exporting_to_file(key: bytes, user_id: int) -> BufferedInputFile:
        pwd_records: list[PasswordRecord] = await db_manager.relational_db.export_passwords(user_id=user_id)

        csv_lines = ['"url","username","password"']
        for pwd_record in pwd_records:
            decrypted_record: DecryptedRecord = PwManUtils.decrypt_record(
                encrypted_record=pwd_record.encrypted_record,
                key=key
            )
            csv_lines.append(f'"{decrypted_record.service}","{decrypted_record.login}","{decrypted_record.password}"')

        csv_content = "\n".join(csv_lines).encode('utf-8')
        buffer = BytesIO(csv_content)

        return BufferedInputFile(file=buffer.read(), filename=f"{user_id}_passwords.csv")

