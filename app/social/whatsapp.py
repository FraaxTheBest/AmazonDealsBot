from app.social.base import PublishResult, SocialPost


class WhatsAppPublisher:
    name = "whatsapp"

    def ready(self) -> tuple[bool, str]:
        return False, "WhatsApp Channel non e' ancora sbloccato/configurato."

    async def publish(self, post: SocialPost) -> PublishResult:
        return PublishResult(self.name, False, message=self.ready()[1])
