import re
import os

LOG_LINE_PATTERN = re.compile(r"\[(.*?)\] (\w+) ([^\s]+) \((.*?)\) (.*)")


def count_lines(filename):
    with open(filename, "rb") as f:
        return sum(1 for line in f)


def parse_log_file(path=None, level=None, logger_filter=None, query=None, lines=None):
    logs = []
    all_loggers = set()

    if lines:
        lines_iter = lines
    elif path and os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            lines_iter = reversed(f.readlines())
    else:
        raise ValueError("Either 'lines' must be provided or a valid 'path' to a log file.")

    current_log = None

    for line in lines_iter:
        match = LOG_LINE_PATTERN.match(line)
        if match:
            # Save the previous log entry if it exists
            if current_log:
                logs.append(current_log)
            timestamp, lvl, logger, location, message = match.groups()
            all_loggers.add(logger)
            # Filter here
            if (level and lvl != level) or (logger_filter and logger != logger_filter):
                current_log = None
                continue
            current_log = {
                "timestamp": timestamp,
                "level": lvl,
                "logger": logger,
                "location": location,
                "message": message.rstrip(),
            }
        else:
            # Continuation of previous log (e.g., traceback)
            if current_log:
                current_log["message"] += "\n" + line.rstrip()
            # else: ignore orphaned lines

    # Don't forget the last log entry
    if current_log:
        logs.append(current_log)

    # Apply query filter at the end (so multi-line messages are included)
    if query:
        query = query.lower()
        logs = [log for log in logs if query in log["message"].lower()]

    return logs, sorted(all_loggers)
