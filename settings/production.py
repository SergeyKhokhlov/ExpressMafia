# TG_TOKEN = "1363841624:AAEbh2XaTpf0wVK6nJaDTY6mxNs4gtpjTBY"
# TG_API_URL = None
import logging.config
import os

import sentry_sdk


# Путь до коренной папки `tele_bot`
BASE_PATH = os.path.dirname(os.path.dirname(__file__))

TG_TOKEN = "2073227161:AAEQcHMYsawinAZpM_0tJlAvyQ8Ggj-oJdc"

# На сервере не используем прокси-URL
TG_API_URL = None

# Sentry
sentry_sdk.init(
    dsn="1363841624:AAEbh2XaTpf0wVK6nJaDTY6mxNs4gtpjTBY",
)
