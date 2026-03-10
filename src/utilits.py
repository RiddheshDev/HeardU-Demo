from langchain_community.utilities import SQLDatabase
from typing import Optional,Dict,Any, Sequence, Literal, Union
from sqlalchemy.engine import URL, Engine, Result 
import asyncio
from src.langgraph.logger_config import logger,structured_log
from src.langgraph.func import db_uri2
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

class PatchedSQLDatabase(SQLDatabase):
    def run_no_throw(
        self,
        command: str,
        fetch: Literal["all", "one"] = "all",
        include_columns: bool = True,  # force True here
        *,
        parameters: Optional[Dict[str, Any]] = None,
        execution_options: Optional[Dict[str, Any]] = None,
    ) -> Union[str, Sequence[Dict[str, Any]], Result[Any]]:
        return super().run_no_throw(
            command,
            fetch=fetch,
            include_columns=include_columns,
            parameters=parameters,
            execution_options=execution_options
        )
    
async def retry_with_backoff(logger, func, *args, max_retries: int = 3, retry_delay = 0.5, **kwargs):
    """Generic retry wrapper with exponential backoff"""
    for attempt in range(1,max_retries+1):
        try:
            if asyncio.iscoroutinefunction(func):
                result= await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            logger.info(f"Function ran perfectly - {func.__name__} - trial {attempt}",module=func.__module__)
            return result
        except Exception as e:
            if attempt == max_retries:
                logger.exception(f"Final attempt failed for {func.__name__}: {str(e)}",module=func.__module__,total_attempts = max_retries, error = type(e).__name__)
                raise
            else:
                # logger.exception(f"Attempt {attempt} failed for {func.__name__}: {str(e)}.",error=type(e).__name__,exc_info=True,attempt=attempt,total_attempts = max_retries)
                logger.warning(f"Attempt {attempt} failed for {func.__name__}: {str(e)}.",module=func.__module__,error=type(e).__name__,attempt=attempt,total_attempts = max_retries)
                await asyncio.sleep(retry_delay)

async def retry_with_backoff2(logger, func, *args, max_retries: int = 3, retry_delay = 0.5, **kwargs):
    """Generic retry wrapper with exponential backoff"""
    for attempt in range(1,max_retries+1):
        try:
            if asyncio.iscoroutinefunction(func):
                result= await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            # logger.info(f"Function ran perfectly - {func.__name__} - trial {attempt}")
            structured_log(logger=logger,level='info',message=f"Function ran perfectly - {func.__name__} - trial {attempt}",function=func.__name__)
            return result
        except Exception as e:
            if attempt == max_retries:
                # logger.exception(f"Final attempt failed for {func.__name__}: {str(e)}",total_attempts = max_retries, error = type(e).__name__)
                structured_log(logger,'exception',message=f"Final attempt failed for {func.__name__}: {str(e)}",total_attempts = max_retries, error = type(e).__name__,function=func.__name__)
                raise
            else:
                # logger.exception(f"Attempt {attempt} failed for {func.__name__}: {str(e)}.",error=type(e).__name__,exc_info=True,attempt=attempt,total_attempts = max_retries)
                # logger.warning(f"Attempt {attempt} failed for {func.__name__}: {str(e)}.",error=type(e).__name__,attempt=attempt,total_attempts = max_retries)
                structured_log(logger,'error',message=f"Attempt {attempt} failed for {func.__name__}: {str(e)}.",error=type(e).__name__,attempt=attempt,total_attempts = max_retries,function=func.__name__)
                await asyncio.sleep(retry_delay)

def extract_last_tool_data(chat_history: list):
    tool_call, tool_output = None, None
    for entry in reversed(chat_history):
        if isinstance(entry, dict) and 'tool_output' in entry and not tool_output:
            tool_output = entry
        elif isinstance(entry, dict) and 'tool_call' in entry and not tool_call:
            tool_call = entry
            break
    return [tool_call, tool_output] if tool_call and tool_output else None

async def get_coupon(config):
    async with AsyncPostgresSaver.from_conn_string(db_uri2()) as conn:
        memory = await conn.aget(config)
        coupon = memory['channel_values'].get('coupon')
        return coupon