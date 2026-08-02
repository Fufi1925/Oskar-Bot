# Lavalink audio node for University Bot.
#
# Deployed as its own Railway service, pointed at this Dockerfile under
# Settings -> Build -> Dockerfile Path: lavalink/Dockerfile
#
# The image is the official one. Pinned to the 4 series rather than
# `latest`, so a major release cannot swap the API version out from
# under the bot -- wavelink 3.x speaks v4 and nothing else.
FROM ghcr.io/lavalink-devs/lavalink:4

# Lavalink reads application.yml from its working directory, which is
# /opt/Lavalink in this image (verified against the image config, not
# assumed). The image runs as the unprivileged `lavalink` user, so the
# file is chowned -- a root-owned config it cannot read makes it fall
# back to defaults, which means no password and no plugins, and the
# failure looks like "everything is fine but nothing plays".
COPY --chown=lavalink:lavalink application.yml /opt/Lavalink/application.yml

# Documentation only; Railway routes by its own $PORT. The value in
# application.yml is what actually binds.
EXPOSE 2333
