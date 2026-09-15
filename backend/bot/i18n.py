"""Bot UI text in English and Uzbek.

Language is auto-detected from the user's Telegram client language on
first /start (``uz`` -> Uzbek, anything else -> English), stored per
tenant in AppConfig.language, and changeable any time via /language.
"""
from __future__ import annotations

SUPPORTED_LANGUAGES = ("en", "uz")
DEFAULT_LANGUAGE = "en"


def detect_language(telegram_language_code: str | None) -> str:
    if isinstance(telegram_language_code, str) and telegram_language_code.lower().startswith("uz"):
        return "uz"
    return DEFAULT_LANGUAGE


_STRINGS: dict[str, dict[str, str]] = {
    "start": {
        "en": "Telegram Conversation Behavioral Analyzer\n\n{export_instructions}",
        "uz": "Telegram Suhbat Xulq-atvor Tahlilchisi\n\n{export_instructions}",
    },
    "export_instructions": {
        "en": (
            "Send me your Telegram chat export and I'll analyze it — nothing leaves "
            "this bot's own server, and only you can ever see your results.\n\n"
            "How to export (Telegram Desktop, not the App Store version — that one "
            "doesn't have this feature):\n"
            "1. Open the chat you want to analyze\n"
            "2. Click the ⋮ menu at the top of the chat → Export chat history\n"
            "3. Set format to JSON (media can stay unchecked, it's not needed)\n"
            "4. Export, then send me the resulting result.json file right here\n\n"
            "Language: /language · O'zbekcha uchun: /language"
        ),
        "uz": (
            "Telegram suhbat eksportingizni menga yuboring — men uni tahlil qilaman. "
            "Hech narsa botning o'z serveridan tashqariga chiqmaydi, natijalaringizni "
            "faqat siz ko'rasiz.\n\n"
            "Qanday eksport qilish kerak (Telegram Desktop orqali, App Store "
            "versiyasida bu funksiya yo'q):\n"
            "1. Tahlil qilmoqchi bo'lgan suhbatni oching\n"
            "2. Suhbat tepasidagi ⋮ menyusini bosing → Export chat history\n"
            "3. Formatni JSON qilib belgilang (media fayllarni belgilash shart emas)\n"
            "4. Eksport qiling va hosil bo'lgan result.json faylini shu yerga yuboring\n\n"
            "Til: /language · For English: /language"
        ),
    },
    "help": {
        "en": (
            "Commands:\n"
            "/overview — totals and headline stats\n"
            "/dashboard — open the full chart dashboard\n"
            "/fastest — fastest observed reply\n"
            "/slowest — slowest observed reply\n"
            "/sessions — conversation session stats\n"
            "/windows — historically responsive windows\n"
            "/ask <question> — ask in plain language\n"
            "/language — switch between English and Uzbek\n\n"
            "Everything here describes historical communication patterns only — "
            "never a claim about intent or availability."
        ),
        "uz": (
            "Buyruqlar:\n"
            "/overview — umumiy statistika\n"
            "/dashboard — to'liq grafik paneli\n"
            "/fastest — eng tez kuzatilgan javob\n"
            "/slowest — eng sekin kuzatilgan javob\n"
            "/sessions — suhbat sessiyalari statistikasi\n"
            "/windows — tarixan eng faol javob vaqtlari\n"
            "/ask <savol> — oddiy tilda savol bering\n"
            "/language — til tanlash (ingliz/o'zbek)\n\n"
            "Bu yerdagi hamma narsa faqat tarixiy muloqot naqshlarini tavsiflaydi — "
            "hech qachon niyat yoki mavjudlik haqida da'vo emas."
        ),
    },
    "choose_language": {
        "en": "Choose your language:",
        "uz": "Tilni tanlang:",
    },
    "language_set": {
        "en": "Language set to English.",
        "uz": "Til o'zbek tiliga o'zgartirildi.",
    },
    "file_too_large": {
        "en": "That file is too large (over 20MB). Try exporting without media.",
        "uz": "Fayl juda katta (20MB dan oshiq). Media fayllarsiz eksport qilib ko'ring.",
    },
    "importing": {
        "en": "Got it — importing your export…",
        "uz": "Qabul qilindi — eksportingiz import qilinmoqda…",
    },
    "invalid_json": {
        "en": "That doesn't look like valid JSON. Make sure you're sending result.json.",
        "uz": "Bu to'g'ri JSON fayl emasga o'xshaydi. result.json faylini yuborayotganingizga ishonch hosil qiling.",
    },
    "group_export_rejected": {
        "en": (
            "This looks like a group/channel export. This tool analyzes one-on-one "
            "conversations only — please export a personal chat."
        ),
        "uz": (
            "Bu guruh/kanal eksportiga o'xshaydi. Bu vosita faqat ikki kishilik "
            "shaxsiy suhbatlarni tahlil qiladi — iltimos, shaxsiy chatni eksport qiling."
        ),
    },
    "only_one_sender": {
        "en": (
            "Imported {count} messages, but I only found one sender in this "
            "export — I need a two-person conversation to analyze response patterns."
        ),
        "uz": (
            "{count} ta xabar import qilindi, lekin bu eksportda faqat bitta "
            "jo'natuvchi topildi — javob naqshlarini tahlil qilish uchun ikki "
            "kishilik suhbat kerak."
        ),
    },
    "import_success": {
        "en": (
            "Imported {count} messages with {other}.\n"
            "Sessions: {sessions} · Response events: {events}\n\n"
            "Tap below to see the full dashboard, or try /overview, /fastest, /ask.{dashboard_note}"
        ),
        "uz": (
            "{other} bilan {count} ta xabar import qilindi.\n"
            "Sessiyalar: {sessions} · Javob hodisalari: {events}\n\n"
            "To'liq paneli ko'rish uchun pastdagi tugmani bosing, yoki /overview, "
            "/fastest, /ask buyruqlarini sinab ko'ring.{dashboard_note}"
        ),
    },
    "dashboard_not_configured_note": {
        "en": "\n\n(Dashboard link not configured yet — ask commands still work.)",
        "uz": "\n\n(Panel havolasi hali sozlanmagan — ask buyruqlari baribir ishlaydi.)",
    },
    "pick_me_prompt": {
        "en": (
            "Imported {count} messages. I couldn't automatically tell which "
            "sender is you — please pick:"
        ),
        "uz": (
            "{count} ta xabar import qilindi. Qaysi jo'natuvchi siz ekanligingizni "
            "avtomatik aniqlay olmadim — iltimos, tanlang:"
        ),
    },
    "pick_me_button": {
        "en": "This is me ({name})",
        "uz": "Bu men ({name})",
    },
    "pick_me_error": {
        "en": "Something went wrong — please resend the export file.",
        "uz": "Nimadir xato ketdi — iltimos, eksport faylini qayta yuboring.",
    },
    "setup_complete": {
        "en": (
            "Set up! Sessions: {sessions} · Response events: {events}\n\n"
            "Tap below to see the full dashboard, or try /overview, /fastest, /ask."
        ),
        "uz": (
            "Sozlandi! Sessiyalar: {sessions} · Javob hodisalari: {events}\n\n"
            "To'liq paneli ko'rish uchun pastdagi tugmani bosing, yoki /overview, "
            "/fastest, /ask buyruqlarini sinab ko'ring."
        ),
    },
    "dashboard_button": {
        "en": "📊 Open Dashboard",
        "uz": "📊 Panelni ochish",
    },
    "dashboard_not_configured": {
        "en": "Dashboard isn't configured on this server yet.",
        "uz": "Panel bu serverda hali sozlanmagan.",
    },
    "dashboard_prompt": {
        "en": "Tap below to open your dashboard:",
        "uz": "Panelingizni ochish uchun pastdagi tugmani bosing:",
    },
    "no_conversation": {
        "en": "No conversation imported yet. Send your export file first.",
        "uz": "Hali hech qanday suhbat import qilinmagan. Avval eksport faylingizni yuboring.",
    },
    "overview_template": {
        "en": (
            "Total messages: {total}\n"
            "{other_name}: {other_count} ({other_pct}%)\n"
            "You: {me_count} ({me_pct}%)\n"
            "Period: {first} to {last}\n"
            "Active days: {active_days}\n"
            "Conversation sessions: {sessions}"
        ),
        "uz": (
            "Jami xabarlar: {total}\n"
            "{other_name}: {other_count} ({other_pct}%)\n"
            "Siz: {me_count} ({me_pct}%)\n"
            "Davr: {first} — {last}\n"
            "Faol kunlar: {active_days}\n"
            "Suhbat sessiyalari: {sessions}"
        ),
    },
    "no_response_yet": {
        "en": "No response events yet — send your export first.",
        "uz": "Hali javob hodisalari yo'q — avval eksportingizni yuboring.",
    },
    "fastest_reply": {
        "en": "Fastest observed reply: {duration}",
        "uz": "Eng tez kuzatilgan javob: {duration}",
    },
    "slowest_reply": {
        "en": (
            "Slowest observed reply: {duration}\n"
            "This is the longest observed delay in the imported history. "
            "The system cannot determine whether the delay was intentional."
        ),
        "uz": (
            "Eng sekin kuzatilgan javob: {duration}\n"
            "Bu import qilingan tarixdagi eng uzoq kuzatilgan kechikish. "
            "Tizim bu kechikish ataylab bo'lganligini aniqlay olmaydi."
        ),
    },
    "no_sessions_yet": {
        "en": "No conversation sessions yet — send your export first.",
        "uz": "Hali suhbat sessiyalari yo'q — avval eksportingizni yuboring.",
    },
    "sessions_template": {
        "en": (
            "Sessions: {count}\n"
            "Average duration: {avg}\n"
            "Median duration: {median}\n"
            "Longest session: {longest}\n"
            "Avg. messages/session: {avg_msgs}"
        ),
        "uz": (
            "Sessiyalar: {count}\n"
            "O'rtacha davomiylik: {avg}\n"
            "Mediana davomiylik: {median}\n"
            "Eng uzoq sessiya: {longest}\n"
            "Sessiya boshiga o'rtacha xabarlar: {avg_msgs}"
        ),
    },
    "windows_not_enough": {
        "en": "Not enough data yet.",
        "uz": "Hozircha yetarli ma'lumot yo'q.",
    },
    "windows_template": {
        "en": "Historically responsive windows:\n{lines}\n\n{note}",
        "uz": "Tarixan eng faol javob vaqtlari:\n{lines}\n\n{note}",
    },
    "ask_usage": {
        "en": "Usage: /ask <question>, e.g. /ask when is she usually most active?",
        "uz": "Foydalanish: /ask <savol>, masalan: /ask u odatda qachon eng faol?",
    },
    "no_answer": {
        "en": "No answer available.",
        "uz": "Javob topilmadi.",
    },
    "import_error": {
        "en": (
            "Something went wrong while importing that file. This has been logged — "
            "please try sending it again in a moment."
        ),
        "uz": (
            "Faylni import qilishda xatolik yuz berdi. Bu qayd etildi — "
            "iltimos, biroz o'tib qayta yuborib ko'ring."
        ),
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    template = _STRINGS.get(key, {}).get(lang) or _STRINGS.get(key, {}).get(DEFAULT_LANGUAGE, key)
    return template.format(**kwargs) if kwargs else template
