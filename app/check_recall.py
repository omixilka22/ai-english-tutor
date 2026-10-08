"""Local configuration check only: no API calls, no keys printed, no meetings joined."""
from app.config import settings
from app.services.recall_client import configured


def main():
    print('Recall API key and region:', 'OK' if configured() else 'missing or invalid')
    secret=settings.RECALL_WEBHOOK_SECRET
    print('Workspace verification secret:', 'configured' if secret and secret.get_secret_value().startswith('whsec_') else 'missing')
    print('Webhook setup confirmed:', 'yes' if settings.RECALL_WEBHOOK_READY else 'no')
    print('No external requests made. API key validity and public tunnel have not been tested.')


if __name__=='__main__':
    main()
