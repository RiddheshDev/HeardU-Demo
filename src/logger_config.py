from loguru import logger
import sys
import traceback

logger.remove()
logger.add(
    "logs/heardu.log",
    level="TRACE",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message} | {file}:{line} | {function} | {extra}",
    # rotation="10 MB",         # Rotate when log reaches 10MB
    # retention="7 days",       # Keep logs for 7 days
    # compression="zip",        # Compress old logs
    backtrace=True,           # Show full error trace
    diagnose=True,
    serialize=True ,
    catch=True          # Include variable values in tracebacks
)

def structured_log(logger,level, message,*args, **kwargs):
    if level =='info':
        logger.info(message,*args,**kwargs)
    elif level=='error':
        logger.error(message,*args,**kwargs)    
    
    elif level =="debug":
        logger.debug(message,*args,**kwargs)
    elif level =='exception':
        logger.exception(message,*args,**kwargs)
