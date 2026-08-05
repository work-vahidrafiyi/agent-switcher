from __future__ import annotations

from importlib.resources import as_file, files
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication


_language = "en"
_default_font: Optional[QFont] = None
_vazirmatn_family: Optional[str] = None

_FA = {
    "Active": "فعال",
    "Add account": "افزودن حساب",
    "Add account...": "افزودن حساب...",
    "Add your first account": "اولین حساب خود را اضافه کنید",
    "After switching, close and reopen VS Code.": "پس از جابه‌جایی، VS Code را ببندید و دوباره باز کنید.",
    "Agent Switcher - no active profile": "Agent Switcher - هیچ پروفایل فعالی نیست",
    "Between 20% and 80% remaining": "بین ۲۰ تا ۸۰ درصد باقی مانده",
    "Browser": "مرورگر",
    "Browser did not open? Use this link": "مرورگر باز نشد؟ از این پیوند استفاده کنید",
    "Cancel": "انصراف",
    "Checking usage": "در حال بررسی سهمیه",
    "Checking usage for {profile}": "در حال بررسی سهمیه {profile}",
    "Close": "بستن",
    "Codex appears to be running and may write auth.json while switching.\n\n{details}\n\nQuit Codex first, or continue anyway?": "به نظر می‌رسد Codex در حال اجراست و ممکن است هنگام جابه‌جایی auth.json را تغییر دهد.\n\n{details}\n\nابتدا Codex را ببندید یا با این حال ادامه می‌دهید؟",
    "Codex is still running": "Codex هنوز در حال اجراست",
    "Collapse usage details": "بستن جزئیات سهمیه",
    "Copied debug info for {profile}.": "اطلاعات اشکال‌زدایی {profile} کپی شد.",
    "Copied.": "کپی شد.",
    "Copy": "کپی",
    "Copy account id and saved profile path": "کپی شناسه حساب و مسیر پروفایل ذخیره‌شده",
    "Copy debug info": "کپی اطلاعات اشکال‌زدایی",
    "Dark": "تیره",
    "Device code": "کد دستگاه",
    "Done": "تمام",
    "Enable global quick-switch hotkey": "فعال‌سازی کلید میانبر سراسری جابه‌جایی سریع",
    "Endpoint": "نشانی",
    "English": "English",
    "Expand usage details": "نمایش جزئیات سهمیه",
    "Failed: {error}": "ناموفق: {error}",
    "Five-hour window": "بازه پنج‌ساعته",
    "From": "از",
    "Get started": "شروع",
    "Give the account a name, then choose how to sign in.": "برای حساب نامی انتخاب کنید، سپس روش ورود را مشخص کنید.",
    "Hide raw output": "پنهان کردن خروجی خام",
    "Language": "زبان",
    "Later": "بعداً",
    "Less than 20% remaining": "کمتر از ۲۰ درصد باقی مانده",
    "Light": "روشن",
    "Low Codex quota": "سهمیه Codex کم است",
    "Low-quota warning threshold": "آستانه هشدار سهمیه کم",
    "Manual fallback link": "پیوند جایگزین دستی",
    "More than 80% remaining": "بیش از ۸۰ درصد باقی مانده",
    "Name": "نام",
    "No": "خیر",
    "Network activity": "فعالیت شبکه",
    "Network route": "مسیر اتصال شبکه",
    "Choose a direct connection or set an HTTP proxy for app requests.": "اتصال مستقیم را انتخاب کنید یا برای درخواست‌های برنامه یک پروکسی HTTP تنظیم کنید.",
    "New name:": "نام جدید:",
    "No account details": "جزئیات حساب موجود نیست",
    "No accounts yet. Add an account to sign in.": "هنوز حسابی ندارید. برای ورود یک حساب اضافه کنید.",
    "No network calls recorded.": "هیچ درخواست شبکه‌ای ثبت نشده است.",
    "No other saved profile is available for Smart pick.": "پروفایل ذخیره‌شده دیگری برای انتخاب هوشمند موجود نیست.",
    "No profile has usable usage data for Smart pick.": "هیچ پروفایلی داده سهمیه قابل استفاده برای انتخاب هوشمند ندارد.",
    "No other profile has fresh usage data with enough headroom.": "هیچ پروفایل دیگری داده تازه با سهمیه آزاد کافی ندارد.",
    "No switches recorded.": "هیچ جابه‌جایی ثبت نشده است.",
    "Not checked": "بررسی نشده",
    "Not enough data yet": "هنوز داده کافی نیست",
    "Offline mode (disable usage checks)": "حالت آفلاین (غیرفعال‌کردن بررسی سهمیه)",
    "Proxy": "پروکسی",
    "No proxy": "بدون پروکسی",
    "Custom HTTP proxy": "پروکسی HTTP دلخواه",
    "HTTP proxy URL": "نشانی پروکسی HTTP",
    "The proxy is used for sign-in, quota checks, and token refresh. Proxy credentials are stored locally in settings.": "پروکسی برای ورود، بررسی سهمیه و تازه‌سازی توکن استفاده می‌شود. اطلاعات ورود پروکسی به‌صورت محلی در تنظیمات ذخیره می‌شود.",
    "Enter an HTTP proxy URL.": "نشانی پروکسی HTTP را وارد کنید.",
    "Enter a valid HTTP proxy URL.": "یک نشانی معتبر برای پروکسی HTTP وارد کنید.",
    "Proxy URL must start with http:// or https://.": "نشانی پروکسی باید با http:// یا https:// شروع شود.",
    "Enter a proxy URL without a path, query, or fragment.": "نشانی پروکسی را بدون مسیر، query یا fragment وارد کنید.",
    "Proxy port must be between 1 and 65535.": "پورت پروکسی باید بین ۱ و ۶۵۵۳۵ باشد.",
    "Offline mode is on - turn it off in settings to check usage": "حالت آفلاین روشن است؛ برای بررسی سهمیه آن را در تنظیمات خاموش کنید",
    "Offline mode is on. Turn it off in settings to check usage.": "حالت آفلاین روشن است. برای بررسی سهمیه آن را در تنظیمات خاموش کنید.",
    "Offline mode is on, so stale usage data cannot be refreshed for Smart pick.": "حالت آفلاین روشن است؛ داده قدیمی سهمیه برای انتخاب هوشمند قابل تازه‌سازی نیست.",
    "Open": "باز کردن",
    "OK": "تأیید",
    "Open Agent Switcher": "باز کردن Agent Switcher",
    "Open browser OAuth sign-in on this computer": "باز کردن ورود OAuth در مرورگر این رایانه",
    "Open the link and enter the code.": "پیوند را باز کنید و کد را وارد کنید.",
    "Persian": "فارسی",
    "Purpose": "هدف",
    "Quit": "خروج",
    "Quick switch": "جابه‌جایی سریع",
    "Refresh all usage": "تازه‌سازی سهمیه همه حساب‌ها",
    "Refresh this account": "تازه‌سازی این حساب",
    "Refresh usage for all accounts": "تازه‌سازی سهمیه همه حساب‌ها",
    "Refreshing stale usage data before Smart pick...": "در حال تازه‌سازی داده قدیمی سهمیه پیش از انتخاب هوشمند...",
    "Remaining trend": "روند سهمیه باقی‌مانده",
    "Remove account": "حذف حساب",
    "Remove failed": "حذف ناموفق بود",
    "Remove {profile}?": "حساب {profile} حذف شود؟",
    "Rename": "تغییر نام",
    "Rename account": "تغییر نام حساب",
    "Rename failed": "تغییر نام ناموفق بود",
    "Reset unavailable": "زمان بازنشانی موجود نیست",
    "Resets {time}": "بازنشانی در {time}",
    "Restart required": "نیاز به راه‌اندازی دوباره",
    "Restart failed": "راه‌اندازی دوباره ناموفق بود",
    "Restart now": "همین حالا راه‌اندازی مجدد",
    "Restart the app after changing language to fully apply text direction and translations.": "پس از تغییر زبان، برنامه را دوباره اجرا کنید تا جهت متن و ترجمه‌ها کامل اعمال شوند.",
    "The app could not start a new process. Please restart it manually.": "برنامه نتوانست فرایند جدیدی اجرا کند. لطفاً آن را دستی دوباره راه‌اندازی کنید.",
    "Result": "نتیجه",
    "Save": "ذخیره",
    "Settings": "تنظیمات",
    "Show a link and one-time code": "نمایش پیوند و کد یک‌بارمصرف",
    "Show raw output": "نمایش خروجی خام",
    "Sign-in failed.": "ورود ناموفق بود.",
    "Sign-in failed: {error}": "ورود ناموفق بود: {error}",
    "Sign-in method": "روش ورود",
    "Sign in through your browser or use a device code. You can add more accounts later.": "از طریق مرورگر وارد شوید یا از کد دستگاه استفاده کنید. بعداً می‌توانید حساب‌های بیشتری اضافه کنید.",
    "Skip": "رد کردن",
    "Skip for now": "فعلاً رد کردن",
    "Smart pick": "انتخاب هوشمند",
    "Smart pick data freshness": "تازگی داده انتخاب هوشمند",
    "Smart pick minimum headroom": "حداقل سهمیه آزاد برای انتخاب هوشمند",
    "Start sign-in": "شروع ورود",
    "Starting device sign-in...": "در حال شروع ورود با کد دستگاه...",
    "Success": "موفق",
    "Switch account": "جابه‌جایی حساب",
    "Switch between saved Codex accounts without replacing credentials by hand.": "بدون جایگزینی دستی اعتبارنامه‌ها، میان حساب‌های ذخیره‌شده Codex جابه‌جا شوید.",
    "Switch failed": "جابه‌جایی ناموفق بود",
    "Switch history": "تاریخچه جابه‌جایی",
    "Switch to this account": "جابه‌جایی به این حساب",
    "Switch to the account with the most usable remaining quota": "جابه‌جایی به حسابی با بیشترین سهمیه قابل استفاده",
    "Switched {previous} to {profile}. Close and reopen VS Code to pick it up.": "از {previous} به {profile} جابه‌جا شد. برای اعمال، VS Code را ببندید و دوباره باز کنید.",
    "System": "سیستم",
    "Theme": "پوسته",
    "This deletes the saved credential file only. The upstream account is untouched.": "فقط فایل اعتبارنامه ذخیره‌شده حذف می‌شود و حساب اصلی تغییری نمی‌کند.",
    "To": "به",
    "Try again": "تلاش دوباره",
    "Unavailable": "ناموجود",
    "Usage has not been checked": "سهمیه بررسی نشده است",
    "Usage not checked": "سهمیه بررسی نشده",
    "Usage unavailable": "سهمیه در دسترس نیست",
    "Use the account rows or tray menu to switch. Settings and usage refresh are available from the header.": "برای جابه‌جایی از ردیف حساب‌ها یا منوی سینی سیستم استفاده کنید. تنظیمات و تازه‌سازی سهمیه در سربرگ هستند.",
    "View network activity": "نمایش فعالیت شبکه",
    "View switch history": "نمایش تاریخچه جابه‌جایی",
    "Waiting for browser...": "در انتظار مرورگر...",
    "Waiting for browser sign-in. The link is available as a manual fallback.": "در انتظار ورود مرورگر هستیم. پیوند به‌عنوان راه جایگزین دستی در دسترس است.",
    "Waiting for browser sign-in to complete...": "در انتظار تکمیل ورود در مرورگر...",
    "Waiting for device sign-in...": "در انتظار ورود با کد دستگاه...",
    "Weekly window": "بازه هفتگی",
    "Welcome": "خوش آمدید",
    "Welcome to Agent Switcher": "به Agent Switcher خوش آمدید",
    "When": "زمان",
    "You're set up": "آماده‌اید",
    "Yes": "بله",
    "{count} account(s) | active: {active}": "{count} حساب | فعال: {active}",
    "{name} already exists. Pick another name.": "نام {name} از قبل وجود دارد. نام دیگری انتخاب کنید.",
    "{profile} - usage unknown": "{profile} - سهمیه نامشخص",
    "{profile} - {five}% left (5h), {weekly}% left (weekly)": "{profile} - پنج‌ساعته: {five}٪ باقی‌مانده، هفتگی: {weekly}٪ باقی‌مانده",
    "{profile} has {remaining}% remaining. Consider checking another account.": "برای {profile} فقط {remaining}٪ باقی مانده است. حساب دیگری را بررسی کنید.",
    "{value}% remaining": "{value}٪ باقی‌مانده",
    "{value} minutes": "{value} دقیقه",
    "% remaining": "٪ باقی‌مانده",
    " minutes": " دقیقه",
    "usage_check": "بررسی سهمیه",
    "token_refresh": "تازه‌سازی توکن",
    "login": "ورود",
    "A usage refresh is already in progress. Try Smart pick again when it finishes.": "تازه‌سازی سهمیه در حال اجراست. پس از پایان دوباره انتخاب هوشمند را امتحان کنید.",
    "Added {profile} and made it active. Reopen VS Code to use it.": "حساب {profile} اضافه و فعال شد. برای استفاده، VS Code را دوباره باز کنید.",
    "Checked {relative}": "بررسی‌شده {relative}",
    "Failed": "ناموفق",
    "From {value}": "از {value}",
    "More info": "اطلاعات بیشتر",
    "Open this link": "این پیوند را باز کنید",
    "Enter this code": "این کد را وارد کنید",
    "1. Open this link": "۱. این پیوند را باز کنید",
    "2. Enter this code": "۲. این کد را وارد کنید",
    "just now": "همین حالا",
    "{value}m ago": "{value} دقیقه پیش",
    "{value}h ago": "{value} ساعت پیش",
    "{value}d ago": "{value} روز پیش",
    "refreshed {value}": "تازه‌شده {value}",
    "none": "هیچ‌کدام",
    "new account": "حساب جدید",
    "unknown": "نامشخص",
    "unknown error": "خطای نامشخص",
    "unavailable": "ناموجود",
    "About": "درباره",
    "About Agent Switcher": "درباره Agent Switcher",
    "Released under the MIT License.": "تحت مجوز MIT منتشر شده است.",
    "Switch saved CLI coding-agent accounts without revoking refresh tokens.": "میان حساب‌های ذخیره‌شده ابزارهای کدنویسی جابه‌جا شوید، بدون لغو توکن‌های تازه‌سازی.",
    "Version {version}": "نسخه {version}",
    "Appearance": "ظاهر",
    "Automation": "خودکارسازی",
    "Back": "قبلی",
    "Browser sign-in is the default. Device code is available for remote sessions.": "ورود با مرورگر حالت پیش‌فرض است. برای نشست‌های راه دور می‌توانید از کد دستگاه استفاده کنید.",
    "Check the result": "نتیجه را بررسی کنید",
    "Choose a sign-in method": "روش ورود را انتخاب کنید",
    "Each row records an outbound request made by the app.": "هر ردیف یک درخواست خروجی برنامه را ثبت می‌کند.",
    "Each row shows the previous and selected profile with its local timestamp.": "هر ردیف پروفایل قبلی و انتخاب‌شده را همراه زمان محلی نشان می‌دهد.",
    "From and to": "مبدأ و مقصد",
    "Guide: {section}": "راهنمای {section}",
    "If the browser does not open, use the captured link. Device mode also shows a one-time code.": "اگر مرورگر باز نشد، از پیوند ثبت‌شده استفاده کنید. حالت دستگاه کد یک‌بارمصرف را هم نشان می‌دهد.",
    "Manual fallback": "راه جایگزین دستی",
    "Next": "بعدی",
    "Offline mode stops quota checks without disabling login or switching.": "حالت آفلاین بررسی سهمیه را متوقف می‌کند، بدون اینکه ورود یا جابه‌جایی حساب غیرفعال شود.",
    "Purpose identifies login, usage checks, or token refresh. Endpoint shows where it went.": "هدف مشخص می‌کند درخواست برای ورود، بررسی سهمیه یا تازه‌سازی توکن بوده و نشانی مقصد آن را نشان می‌دهد.",
    "Raw output shows the underlying Codex login process without changing the login logic.": "خروجی خام فرایند ورود Codex را بدون تغییر منطق ورود نشان می‌دهد.",
    "Recent switches": "جابه‌جایی‌های اخیر",
    "Replay onboarding": "نمایش دوباره راهنمای شروع",
    "Show guide for this page": "نمایش راهنمای این صفحه",
    "Step {current} of {total}": "مرحله {current} از {total}",
    "Success or failure is recorded locally so unexpected network activity can be reviewed.": "موفقیت یا شکست به‌صورت محلی ثبت می‌شود تا فعالیت شبکه غیرمنتظره قابل بررسی باشد.",
    "Theme changes apply immediately. Language changes fully apply after restart.": "تغییر پوسته فوراً اعمال می‌شود. تغییر زبان پس از راه‌اندازی دوباره کامل اعمال خواهد شد.",
    "This view lists account switches from newest to oldest.": "این نما جابه‌جایی حساب‌ها را از جدیدترین به قدیمی‌ترین نشان می‌دهد.",
    "Troubleshooting": "رفع اشکال",
    "Usage controls": "کنترل‌های سهمیه",
    "Warning thresholds, Smart pick freshness, and the global hotkey are configured here.": "آستانه هشدار، تازگی داده انتخاب هوشمند و کلید میانبر سراسری از اینجا تنظیم می‌شوند.",
    "What this view shows": "این نما چه چیزی نشان می‌دهد",
    "Why a request happened": "دلیل ارسال درخواست",
}


def set_language(language: str) -> None:
    global _language
    _language = language if language in {"en", "fa"} else "en"


def language() -> str:
    return _language


def is_rtl() -> bool:
    return _language == "fa"


def tr(source: str, **values: object) -> str:
    template = _FA.get(source, source) if _language == "fa" else source
    return template.format(**values) if values else template


def configure_i18n(app: QApplication, language_name: str) -> None:
    global _default_font, _vazirmatn_family
    if _default_font is None:
        _default_font = QFont(app.font())
    set_language(language_name)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_rtl() else Qt.LayoutDirection.LeftToRight)

    if not is_rtl():
        app.setFont(QFont(_default_font))
        return

    if _vazirmatn_family is None:
        resource = files("agent_switcher.gui").joinpath("fonts/Vazirmatn-Regular.ttf")
        with as_file(resource) as font_path:
            font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        _vazirmatn_family = families[0] if families else "Vazirmatn"
    font = QFont(_default_font)
    font.setFamily(_vazirmatn_family)
    app.setFont(font)
