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


class FacebookPublisher:
    name = "facebook"

    def __init__(self, settings: Settings):
        self.settings = settings

    def ready(self) -> tuple[bool, str]:
        if not self.settings.social_facebook_enabled:
            return False, "Facebook e' disattivato nel .env."
        if not (self.settings.facebook_page_id or "").strip():
            return False, "FACEBOOK_PAGE_ID mancante."
        if not (
            _secret_value(self.settings.facebook_page_access_token)
            or _secret_value(self.settings.meta_system_user_access_token)
        ):
            return False, (
                "Serve FACEBOOK_PAGE_ACCESS_TOKEN oppure "
                "META_SYSTEM_USER_ACCESS_TOKEN."
            )
        return True, "Pronto"

    async def _resolve_page_token(
        self,
        client: httpx.AsyncClient,
        page_id: str,
        api_root: str,
    ) -> tuple[str, str | None]:
        """Restituisce un Page Access Token senza stamparlo nei log.

        Se FACEBOOK_PAGE_ACCESS_TOKEN e' configurato lo usa direttamente.
        Altrimenti prova a ricavarlo dal System User token assegnato alla Pagina.
        """
        configured = _secret_value(self.settings.facebook_page_access_token)
        if configured:
            return configured, None

        system_token = _secret_value(self.settings.meta_system_user_access_token)
        if not system_token:
            return "", "META_SYSTEM_USER_ACCESS_TOKEN mancante."

        try:
            response = await client.get(
                f"{api_root}/{page_id}",
                params={"fields": "id,name,access_token"},
                headers={"Authorization": f"Bearer {system_token}"},
            )
        except httpx.HTTPError as exc:
            return "", f"Errore rete mentre ricavo il Page token: {exc}"

        try:
            data = response.json()
        except ValueError:
            data = {"body": response.text[:1000]}

        if response.is_error or "error" in data:
            error = data.get("error", {}) if isinstance(data, dict) else {}
            message = error.get("message") or f"HTTP {response.status_code}"
            return "", f"Impossibile ottenere Page Access Token: {message}"

        page_token = str(data.get("access_token") or "").strip()
        if not page_token:
            return "", (
                "Meta non ha restituito il Page Access Token. "
                "Configura FACEBOOK_PAGE_ACCESS_TOKEN nel .env."
            )
        return page_token, None

    async def publish(self, post: SocialPost) -> PublishResult:
        ready, reason = self.ready()
        if not ready:
            return PublishResult(self.name, False, message=reason)

        page_id = (self.settings.facebook_page_id or "").strip()
        version = self.settings.meta_graph_api_version.strip().lstrip("/")
        api_root = f"https://graph.facebook.com/{version}"
        base = f"{api_root}/{page_id}"

        caption = post.text(include_link=True, include_hashtags=True)
        if not caption:
            return PublishResult(self.name, False, message="Il post e' vuoto.")

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.social_http_timeout_seconds
            ) as client:
                page_token, token_error = await self._resolve_page_token(
                    client,
                    page_id,
                    api_root,
                )
                if token_error:
                    return PublishResult(self.name, False, message=token_error)

                headers = {"Authorization": f"Bearer {page_token}"}

                if post.image_url.strip():
                    response = await client.post(
                        f"{base}/photos",
                        data={
                            "url": post.image_url.strip(),
                            "caption": caption[:12000],
                            "published": "true",
                        },
                        headers=headers,
                    )
                else:
                    payload = {"message": caption[:12000]}
                    if post.link.strip():
                        payload["link"] = post.link.strip()
                    response = await client.post(
                        f"{base}/feed",
                        data=payload,
                        headers=headers,
                    )
        except httpx.HTTPError as exc:
            return PublishResult(self.name, False, message=f"Errore rete Facebook: {exc}")

        try:
            data = response.json()
        except ValueError:
            data = {"body": response.text[:1000]}

        if response.is_error or "error" in data:
            error = data.get("error", {}) if isinstance(data, dict) else {}
            message = error.get("message") or f"HTTP {response.status_code}"
            code = error.get("code")
            suffix = f" (codice {code})" if code is not None else ""
            return PublishResult(
                self.name,
                False,
                message=f"Facebook: {message}{suffix}",
                raw=data,
            )

        external_id = str(data.get("post_id") or data.get("id") or "").strip() or None
        return PublishResult(
            self.name,
            True,
            external_id=external_id,
            message="Pubblicato su Facebook.",
            raw=data,
        )
