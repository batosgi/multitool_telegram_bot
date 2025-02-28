from dotenv import load_dotenv

load_dotenv()

from .bot_config import BotConfig
from .pwd_mgr_config import PasswordManagerConfig
from database import DatabaseManager
from database.postgresql import PostgresqlManager
from database.redis import RedisManager

bot_cfg = BotConfig()
pwd_mgr_cfg = PasswordManagerConfig()
db_manager: DatabaseManager = DatabaseManager(
    key_value_db=RedisManager(),
    relational_db=PostgresqlManager()
)

__all__ = (
    "bot_cfg",
    "db_manager",
    "pwd_mgr_cfg"
)
