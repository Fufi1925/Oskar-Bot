# The status bot runs as its own Railway service.
#
# Not a second process in the main container: when Railway restarts that
# container, the deploy fails, or restartPolicyMaxRetries is used up,
# every process in it dies together -- including the watcher, exactly
# when it is supposed to report. Two containers die separately, which is
# the entire reason this is a separate service.

FROM python:3.11-slim

WORKDIR /app

COPY statusbot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY statusbot/ ./statusbot/

# The message builder is shared with the main bot rather than copied.
# Two versions of "how do we turn dashboard JSON into a Discord message"
# would drift apart, and the day they do, a changelog looks different
# depending on which bot sent it. It only imports discord, so it carries
# nothing else along.
COPY bot/utils/message_builder.py ./statusbot/message_builder.py

ENV PYTHONUNBUFFERED=1

# Where the uptime record goes. Attach a Railway volume mounted here,
# or the history restarts on every deploy -- Railway's filesystem is
# wiped each time. Without one the panel simply omits the uptime line
# rather than printing a figure built from the last twenty minutes.
#
# No VOLUME instruction: Railway rejects the build outright with
# "docker VOLUME at Line N is not supported, use Railway Volumes".
ENV STATUS_DATA_DIR=/data

CMD ["python", "statusbot/status_bot.py"]
