import asyncio

import httpx

from app.config import Settings
from app.social.base import PublishResult, SocialPost


def _secret_value(value) -> str:
    if value is None:
        return ""
    try:
        return value.get_secret_value().strip()
    except AttributeError:
        return str(value).strip()


class InstagramPublisher:
    name = "instagram"

    def __init__(self, settings: Settings):
        self.settings = settings

    def ready(self) -> tuple[bool, str]:
        if not self.settings.social_instagram_enabled:
            return False, "Instagram e' disattivato nel .env."
        if not (self.settings.instagram_account_id or "").strip():
            return False, "INSTAGRAM_ACCOUNT_ID mancante."
        if not _secret_value(self.settings.instagram_access_token):
            return False, "INSTAGRAM_ACCESS_TOKEN mancante."
        return True, "Pronto"

    async def publish(self, post: SocialPost) -> PublishResult:
        ready, reason = self.ready()
        if not ready:
            return PublishResult(self.name, False, message=reason)

        if not post.image_url.strip():
            return PublishResult(
                self.name,
                False,
                message=(
                    "Instagram richiede un URL pubblico dell'immagine. "
                    "In Phase 1 incolla l'URL pubblico del Pin/immagine."
                ),
            )

        account_id = (self.settings.instagram_account_id or "").strip()
        token = _secret_value(self.settings.instagram_access_token)
        version = self.settings.meta_graph_api_version.strip().lstrip("/")
        api_root = f"https://graph.instagram.com/{version}"
        # Instagram non rende cliccabili gli URL inseriti nella caption.
        # Manteniamo quindi il link fuori dal testo del post e, quando la
        # bozza contiene un URL, mostriamo una CTA breve verso il link in bio.
        caption_parts: list[str] = []
        if post.title.strip():
            caption_parts.append(post.title.strip())
        if post.description.strip():
            caption_parts.append(post.description.strip())
        if post.link.strip():
            caption_parts.append("🔗 Link in bio")
        if post.hashtags.strip():
            caption_parts.append(post.hashtags.strip())
        caption = "\n\n".join(caption_parts).strip()[:2200]
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.social_http_timeout_seconds
            ) as client:
                create_response = await client.post(
                    f"{api_root}/{account_id}/media",
                    data={
                        "image_url": post.image_url.strip(),
                        "caption": caption,
                    },
                    headers=headers,
                )

                try:
                    create_data = create_response.json()
                except ValueError:
                    create_data = {"body": create_response.text[:1000]}

                if create_response.is_error or "error" in create_data:
                    error = create_data.get("error", {}) if isinstance(create_data, dict) else {}
                    message = error.get("message") or f"HTTP {create_response.status_code}"
                    return PublishResult(
                        self.name,
                        False,
                        message=f"Instagram container: {message}",
                        raw=create_data,
                    )

                creation_id = str(create_data.get("id") or "").strip()
                if not creation_id:
                    return PublishResult(
                        self.name,
                        False,
                        message="Instagram non ha restituito l'ID del container.",
                        raw=create_data,
                    )

                container_ready = False
                last_status = ""
                for attempt in range(6):
                    if attempt:
                        await asyncio.sleep(2)
                    status_response = await client.get(
                        f"{api_root}/{creation_id}",
                        params={"fields": "status_code,status"},
                        headers=headers,
                    )
                    try:
                        status_data = status_response.json()
                    except ValueError:
                        status_data = {"body": status_response.text[:1000]}

                    if status_response.is_error or "error" in status_data:
                        error = status_data.get("error", {}) if isinstance(status_data, dict) else {}
                        message = error.get("message") or f"HTTP {status_response.status_code}"
                        return PublishResult(
                            self.name,
                            False,
                            message=f"Instagram stato container: {message}",
                            raw=status_data,
                        )

                    status_code = str(status_data.get("status_code") or "").upper()
                    last_status = str(status_data.get("status") or status_code or "in elaborazione")
                    if status_code == "FINISHED":
                        container_ready = True
                        break
                    if status_code in {"ERROR", "EXPIRED"}:
                        return PublishResult(
                            self.name,
                            False,
                            message=f"Instagram container non pubblicabile: {last_status}",
                            raw=status_data,
                        )

                if not container_ready:
                    return PublishResult(
                        self.name,
                        False,
                        message=f"Instagram container non ancora pronto: {last_status}",
                    )

                publish_response = await client.post(
                    f"{api_root}/{account_id}/media_publish",
                    data={"creation_id": creation_id},
                    headers=headers,
                )
                try:
                    publish_data = publish_response.json()
                except ValueError:
                    publish_data = {"body": publish_response.text[:1000]}

                if publish_response.is_error or "error" in publish_data:
                    error = publish_data.get("error", {}) if isinstance(publish_data, dict) else {}
                    message = error.get("message") or f"HTTP {publish_response.status_code}"
                    return PublishResult(
                        self.name,
                        False,
                        message=f"Instagram publish: {message}",
                        raw=publish_data,
                    )

                media_id = str(publish_data.get("id") or "").strip() or None
                return PublishResult(
                    self.name,
                    True,
                    external_id=media_id,
                    message="Pubblicato su Instagram.",
                    raw=publish_data,
                )
        except httpx.HTTPError as exc:
            return PublishResult(self.name, False, message=f"Errore rete Instagram: {exc}")
