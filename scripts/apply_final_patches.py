"""Patch idempotenti per i file grandi già presenti nel progetto.

Eseguire UNA volta dalla root del repository:
    python scripts/apply_final_patches.py

Il programma non cancella il database e si ferma se incontra una versione
inaspettata, invece di modificare il file alla cieca.
"""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new in text:
        return text, False
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: atteso 1 blocco, trovati {count}.")
    return text.replace(old, new, 1), True


def patch_posts() -> bool:
    path = ROOT / "app" / "posts.py"
    text = path.read_text(encoding="utf-8")
    original = text

    import_anchor = "from app.affiliate import (\n    affiliate_admin_text,\n    apply_affiliate_link,\n)\n"
    extra_imports = import_anchor + "from app.affiliate_store import get_effective_partner_tag\nfrom app.ai_service import enhance_product_with_ai\nfrom app.amazon.provider_factory import get_product_for_channel\nfrom app.dedupe_store import record_publication\nfrom app.shortlink_service import build_offer_url\n"
    text, _ = replace_once(text, import_anchor, extra_imports, "posts imports")

    # Pulsante bozza nel preview manuale.
    image_row = '''            [\n                InlineKeyboardButton(\n                    text=(\n                        "🖼 Cambia immagine"\n                    ),\n                    callback_data=(\n                        "post:image_menu"\n                    ),\n                )\n            ],\n'''
    image_plus_draft = image_row + '''            [\n                InlineKeyboardButton(\n                    text="📝 SALVA BOZZA",\n                    callback_data="post:save_draft",\n                )\n            ],\n'''
    text, _ = replace_once(text, image_row, image_plus_draft, "preview bozza")

    old_keyboard = '''def published_keyboard(\n    product: ProductSnapshot,\n) -> InlineKeyboardMarkup:\n    return InlineKeyboardMarkup(\n        inline_keyboard=[\n            [\n                InlineKeyboardButton(\n                    text=(\n                        "Vedi offerta 👀"\n                    ),\n                    url=get_public_url(\n                        product\n                    ),\n                )\n            ]\n        ]\n    )\n'''
    new_keyboard = '''def published_keyboard(\n    product: ProductSnapshot,\n    url: str | None = None,\n) -> InlineKeyboardMarkup:\n    return InlineKeyboardMarkup(\n        inline_keyboard=[\n            [\n                InlineKeyboardButton(\n                    text="Vedi offerta 👀",\n                    url=(url or get_public_url(product)),\n                )\n            ]\n        ]\n    )\n'''
    text, _ = replace_once(text, old_keyboard, new_keyboard, "published keyboard")

    text = text.replace(
        '"⚠️ Dati prodotto ancora MOCK."',
        '"ℹ️ Dati dal provider Amazon configurato."',
    )

    # Ricezione prodotto: provider e Tracking ID specifici per canale.
    marker_a = "# =========================================================\n# RICEZIONE PRODOTTO\n# ========================================================="
    marker_b = "# =========================================================\n# IMAGE MENU\n# ========================================================="
    a = text.index(marker_a)
    b = text.index(marker_b, a)
    chunk = text[a:b]

    old_provider = '''    #\n    # 1. Recuperiamo prodotto\n    #\n    product = (\n        await amazon_provider\n        .get_product(\n            asin\n        )\n    )\n\n    #\n    # 2. Affiliate Engine\n    #\n    settings = get_settings()\n'''
    new_provider = '''    #\n    # 1. Recuperiamo prodotto dal provider configurato\n    #    usando il canale selezionato.\n    #\n    settings = get_settings()\n    state_data = await state.get_data()\n    selected_channel_id = state_data.get("channel_id")\n    if selected_channel_id is None:\n        await message.answer("❌ Sessione scaduta. Seleziona di nuovo il canale.")\n        return\n\n    product = await get_product_for_channel(\n        asin=asin,\n        owner_telegram_user_id=settings.admin_user_id,\n        channel_id=int(selected_channel_id),\n    )\n\n    #\n    # 2. Affiliate Engine\n    #\n'''
    chunk, _ = replace_once(chunk, old_provider, new_provider, "manual provider")

    old_tag = '''            expected_partner_tag=(\n                settings.amazon_partner_tag\n            ),'''
    new_tag = '''            expected_partner_tag=(\n                await get_effective_partner_tag(\n                    settings.admin_user_id,\n                    int(selected_channel_id),\n                )\n            ),'''
    chunk, _ = replace_once(chunk, old_tag, new_tag, "manual affiliate tag")
    text = text[:a] + chunk + text[b:]

    # Pubblicazione manuale: AI opzionale, shortlink, storico.
    marker_a = "# =========================================================\n# PUBBLICAZIONE\n# ========================================================="
    marker_b = "# =========================================================\n# CANCELLA POST\n# ========================================================="
    a = text.index(marker_a)
    b = text.index(marker_b, a)
    chunk = text[a:b]

    render_anchor = '''    rendered_post = (\n        await render_saved_template(\n            product\n        )\n    )\n'''
    render_new = '''    # AI opzionale: in caso di errore continuiamo con il prodotto originale.\n    try:\n        ai_result = await enhance_product_with_ai(\n            settings.admin_user_id,\n            product,\n        )\n        product = ai_result.product\n    except Exception:\n        pass\n\n    rendered_post = (\n        await render_saved_template(\n            product\n        )\n    )\n'''
    chunk, _ = replace_once(chunk, render_anchor, render_new, "manual AI")

    old_post_text = '''    post_text = (\n        rendered_post\n        + "\\n\\n"\n        "⚠️ <i>Dati demo: "\n        "provider Amazon reale "\n        "non ancora collegato.</i>"\n    )\n'''
    new_post_text = '''    post_text = rendered_post\n    if settings.amazon_provider == "demo":\n        post_text += (\n            "\\n\\n⚠️ <i>Dati demo: provider Amazon reale "\n            "non ancora collegato.</i>"\n        )\n\n    try:\n        public_url = await build_offer_url(\n            owner_telegram_user_id=settings.admin_user_id,\n            channel_id=channel.id,\n            product=product,\n        )\n    except Exception:\n        public_url = get_public_url(product)\n'''
    chunk, _ = replace_once(chunk, old_post_text, new_post_text, "manual text/shortlink")

    old_send = '''        await send_product_post(\n            bot=bot,\n            chat_id=(\n                channel.telegram_chat_id\n            ),\n            product=product,\n            text=post_text,\n            reply_markup=(\n                published_keyboard(\n                    product\n                )\n            ),\n        )'''
    new_send = '''        sent_message = await send_product_post(\n            bot=bot,\n            chat_id=(\n                channel.telegram_chat_id\n            ),\n            product=product,\n            text=post_text,\n            reply_markup=(\n                published_keyboard(\n                    product,\n                    public_url,\n                )\n            ),\n        )'''
    chunk, _ = replace_once(chunk, old_send, new_send, "manual send")

    after_try = '''    except TelegramAPIError:\n        await query.answer(\n            "❌ Pubblicazione fallita.",\n            show_alert=True,\n        )\n\n        return\n\n    await state.clear()\n'''
    after_new = '''    except TelegramAPIError:\n        await query.answer(\n            "❌ Pubblicazione fallita.",\n            show_alert=True,\n        )\n\n        return\n\n    try:\n        await record_publication(\n            owner_telegram_user_id=settings.admin_user_id,\n            channel_id=channel.id,\n            product=product,\n            source="manual",\n            telegram_message_id=sent_message.message_id,\n        )\n    except Exception:\n        pass\n\n    await state.clear()\n'''
    chunk, _ = replace_once(chunk, after_try, after_new, "manual history")
    text = text[:a] + chunk + text[b:]

    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def patch_scheduling() -> bool:
    path = ROOT / "app" / "scheduling.py"
    text = path.read_text(encoding="utf-8")
    original = text
    old = '''    post_text = (\n        rendered_post\n        + "\\n\\n"\n        "⚠️ <i>Dati demo: "\n        "provider Amazon reale "\n        "non ancora collegato.</i>"\n    )\n'''
    new = '''    post_text = rendered_post\n    if settings.amazon_provider == "demo":\n        post_text += (\n            "\\n\\n⚠️ <i>Dati demo: provider Amazon reale "\n            "non ancora collegato.</i>"\n        )\n'''
    text, _ = replace_once(text, old, new, "scheduled demo warning")
    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def patch_autoposting_demo() -> bool:
    path = ROOT / "app" / "autoposting.py"
    text = path.read_text(encoding="utf-8")
    original = text
    pairs = {
        'asin="B0DEMO0001",\n': 'asin="B0DEMO0001",\n        offer_type="lightning",\n',
        'asin="B0DEMO0002",\n': 'asin="B0DEMO0002",\n        offer_type="coupon",\n',
        'asin="B0DEMO0003",\n': 'asin="B0DEMO0003",\n        offer_type="lowest",\n',
        'asin="B0DEMO0004",\n': 'asin="B0DEMO0004",\n        offer_type="normal",\n',
        'asin="B0DEMO0005",\n': 'asin="B0DEMO0005",\n        offer_type="normal",\n',
    }
    for old, new in pairs.items():
        if new in text:
            continue
        if old not in text:
            raise RuntimeError(f"autopost demo: ASIN anchor mancante: {old.strip()}")
        text = text.replace(old, new, 1)
    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False



def patch_queue_ui() -> bool:
    path = ROOT / "app" / "autopost_queue_ui.py"
    text = path.read_text(encoding="utf-8")
    original = text
    blocks = [
        (
            "    await query.answer(\n        \"Candidato scartato.\"\n    )\n\n    await show_pending(\n",
            "    await show_pending(\n",
        ),
        (
            "    await query.answer(\n        \"Candidato riportato in attesa.\"\n    )\n\n    await show_pending(\n",
            "    await show_pending(\n",
        ),
    ]
    for old, new in blocks:
        if old in text:
            text = text.replace(old, new, 1)
    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def patch_deal_engine() -> bool:
    # Score adattivo: nessun dato inventato quando il provider non espone
    # rating, recensioni o fulfillment.
    path = ROOT / "app" / "deal_engine.py"
    text = path.read_text(encoding="utf-8")
    original = text

    old = '''    score = (
        score_discount
        + score_savings
        + score_rating
        + score_reviews
        + score_availability
        + score_fulfillment
    )

    # Protezione futura:
    # lo score non supera mai 100.
    score = min(
        max(score, 0),
        100,
    )
'''

    new = '''    raw_score = (
        score_discount
        + score_savings
        + score_rating
        + score_reviews
        + score_availability
        + score_fulfillment
    )

    # Alcuni provider ufficiali non espongono tutte le componenti (es.
    # rating/numero recensioni/fulfillment). Non inventiamo dati e non
    # penalizziamo automaticamente un'offerta soltanto per un campo che il
    # provider non può restituire. Normalizziamo lo score sul massimo delle
    # componenti effettivamente osservabili. Con il provider DEMO, che ha
    # tutti i dati, il risultato rimane identico alle fasi precedenti.
    available_max = 50  # sconto: componente sempre richiesta dal Deal Engine

    if savings is not None:
        available_max += 10
    if product.rating is not None:
        available_max += 15
    if product.reviews_count is not None:
        available_max += 10
    if product.availability:
        available_max += 10
    if product.ships_from is not None:
        available_max += 5

    if available_max > 0 and available_max < 100:
        score = int(round(raw_score * 100 / available_max))
    else:
        score = raw_score

    score = min(max(score, 0), 100)
'''

    text, _ = replace_once(text, old, new, "deal engine adaptive score")

    reason_anchor = '''    # -----------------------------------------------------
    # VERDETTO
    # -----------------------------------------------------
'''
    reason_new = '''    if available_max < 100:
        reasons.append(
            f"Score adattato ai dati disponibili ({available_max}/100 componenti osservabili)."
        )

''' + reason_anchor
    text, _ = replace_once(text, reason_anchor, reason_new, "deal engine reason")

    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> int:
    try:
        changes = {
            "app/posts.py": patch_posts(),
            "app/scheduling.py": patch_scheduling(),
            "app/autoposting.py": patch_autoposting_demo(),
            "app/autopost_queue_ui.py": patch_queue_ui(),
            "app/deal_engine.py": patch_deal_engine(),
        }
    except Exception as exc:
        print(f"ERRORE PATCH: {exc}")
        print("Nessun git push: mandami questo output e controlliamo il file.")
        return 1

    for path, changed in changes.items():
        print(f"{'PATCH OK' if changed else 'GIÀ OK  '} | {path}")
    print("Patch finali completate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
