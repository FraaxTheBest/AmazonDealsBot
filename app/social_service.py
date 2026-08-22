from __future__ import annotations

from dataclasses import asdict

from app.config import Settings, get_settings
from app.social.facebook import FacebookPublisher
from app.social.instagram import InstagramPublisher
from app.social.pinterest import PinterestPublisher
from app.social.telegram import TelegramSocialPublisher
from app.social.whatsapp import WhatsAppPublisher
from app.social_store import (
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_PUBLISHED,
    SocialDraft,
    save_publish_results,
)


PLATFORM_LABELS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "pinterest": "Pinterest",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
}


class SocialService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.publishers = {
            "facebook": FacebookPublisher(self.settings),
            "instagram": InstagramPublisher(self.settings),
            "pinterest": PinterestPublisher(),
            "telegram": TelegramSocialPublisher(),
            "whatsapp": WhatsAppPublisher(),
        }

    def platform_status(self, platform: str) -> tuple[bool, str]:
        publisher = self.publishers.get(platform)
        if publisher is None:
            return False, "Piattaforma sconosciuta."
        return publisher.ready()

    def ready_platforms(self) -> list[str]:
        return [name for name in self.publishers if self.platform_status(name)[0]]

    def statuses(self) -> dict[str, tuple[bool, str]]:
        return {name: self.platform_status(name) for name in self.publishers}

    async def publish_draft(self, owner_id: int, draft: SocialDraft) -> dict:
        selected = draft.destinations()
        if not selected:
            return {
                "status": STATUS_FAILED,
                "results": {},
                "message": "Nessuna destinazione selezionata.",
            }

        results: dict[str, dict] = {}
        successes = 0
        attempted = 0

        for platform in selected:
            ready, reason = self.platform_status(platform)
            if not ready:
                results[platform] = {
                    "success": False,
                    "message": reason,
                    "skipped": True,
                }
                continue

            attempted += 1
            result = await self.publishers[platform].publish(draft.post())
            result_dict = asdict(result)
            # Evita di persistere risposte API complete che potrebbero contenere
            # metadati non necessari. Conserviamo solo esito/id/messaggio.
            result_dict.pop("raw", None)
            results[platform] = result_dict
            if result.success:
                successes += 1

        if attempted == 0:
            status = STATUS_FAILED
        elif successes == attempted:
            status = STATUS_PUBLISHED
        elif successes > 0:
            status = STATUS_PARTIAL
        else:
            status = STATUS_FAILED

        await save_publish_results(owner_id, draft.id, results, status)
        return {"status": status, "results": results}
