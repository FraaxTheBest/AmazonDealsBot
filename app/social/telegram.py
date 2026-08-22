from app.social.base import PublishResult, SocialPost


class TelegramSocialPublisher:
    name = "telegram"

    def ready(self) -> tuple[bool, str]:
        return False, "Telegram Social non e' ancora configurato."

    async def publish(self, post: SocialPost) -> PublishResult:
        return PublishResult(self.name, False, message=self.ready()[1])
