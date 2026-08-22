from app.social.base import PublishResult, SocialPost


class PinterestPublisher:
    name = "pinterest"

    def ready(self) -> tuple[bool, str]:
        return False, "Pinterest e' bloccato: attendiamo l'approvazione API."

    async def publish(self, post: SocialPost) -> PublishResult:
        return PublishResult(self.name, False, message=self.ready()[1])
