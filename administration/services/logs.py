import re
import os

LOG_LINE_PATTERN = re.compile(r"\[(.*?)\] (\w+) ([^\s]+) \((.*?)\) (.*)")


def parse_log_file(path, level=None, logger_filter=None, query=None):
    logs = []
    all_loggers = set()

    if not os.path.exists(path):
        return logs, all_loggers

    with open(path, encoding="utf-8", errors="replace") as f:
        lines = reversed(f.readlines())

    for line in lines:
        match = LOG_LINE_PATTERN.match(line)
        if not match:
            continue

        timestamp, lvl, logger, location, message = match.groups()
        all_loggers.add(logger)

        if level and lvl != level:
            continue
        if logger_filter and logger != logger_filter:
            continue
        if query and query not in message.lower():
            continue

        logs.append(
            {
                "timestamp": timestamp,
                "level": lvl,
                "logger": logger,
                "location": location,
                "message": message,
            }
        )

    return logs, all_loggers
