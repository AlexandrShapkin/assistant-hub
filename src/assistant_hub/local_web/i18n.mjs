// User-interface language is deliberately ephemeral; authentication state remains separate.
export const DEFAULT_LOCALE = 'ru';
export const LOCALES = Object.freeze(['ru', 'en']);
const en = {
  pageTitle: 'Assistant Hub · Local workspace',
  localWorkspace: 'LOCAL WORKSPACE',
  syntheticBanner: 'Synthetic sources and manual local calendar import; no external actions.',
  publicBanner: 'Public read-only sources, synthetic fixtures and optional local iCalendar import. No outgoing actions.',
  bannerNote: 'Workflow statuses persist locally. Nothing is sent. Refresh requires login again.',
  loginTitle: 'Your local workspace', loginHint: 'Sign in with the owner password enrolled on this computer.',
  ownerPassword: 'Owner password', signIn: 'Sign in',
  workspace: 'YOUR WORKSPACE', headline1: 'One place.', headline2: 'A clearer picture.',
  service: 'Service', account: 'Account', workflowStatus: 'Workflow status',
  allStatuses: 'All statuses', allServices: 'All services', allAccounts: 'All accounts',
  collect: 'Collect events', collectHint: 'Collects one page for the selected account, or all accounts if none selected.',
  logout: 'Log out', overview: 'ACTIVITY OVERVIEW', inbox: 'Inbox', search: 'Search activity',
  searchPlaceholder: 'Search titles, content, identities…', detailsAria: 'Selected item details',
  itemDetails: 'Item details', selectPrompt: 'Select an item to review its workflow status.',
  footer: 'Pre-alpha · Localhost only · Private manual calendar import · No dispatch',
  noscript: 'JavaScript modules are required for this local application.',
  detailStatus: 'Workflow status (UI only)', save: 'Save status',
  saved: 'Workflow status saved locally. No action dispatched.',
  itemCount: '{count} items',
  empty: 'No matching items. Collect events to populate the inbox.',
  signedIn: 'Signed in. Collection is read-only and manual.',
  collected: 'Page collected. Repeated collection deduplicates; public snapshots can miss updates.',
  loggedOut: 'Logged out. Session revoked.',
  requestFailed: 'Request failed. Use the exact localhost URL and sign in again if needed.',
  calendarEyebrow: 'PERSONAL TIMETABLE',
  calendarTitle: 'Classes by week',
  calendarHint: 'Export one week as an iCal (.ics) file and import it here. No university site requests are made.',
  calendarFile: 'iCalendar file (.ics)', calendarImport: 'Import week',
  calendarWeek: 'Week starting', calendarNone: 'No weeks imported yet.',
  calendarNoClasses: 'No classes', calendarUpdated: 'Last calendar update: {date} UTC',
  calendarSaved: 'Imported {count} classes; changed {changed}, removed {removed}.',
  calendarBadFile: 'Select one .ics file up to 96 KiB.',
  languageAria: 'Interface language',
  'status.new': 'New', 'status.review': 'Review', 'status.deferred': 'Deferred', 'status.done': 'Done',
};
const ru = {
  pageTitle: 'Assistant Hub · Личное пространство',
  localWorkspace: 'ЛИЧНОЕ ПРОСТРАНСТВО',
  syntheticBanner: 'Учебные источники и ручной импорт календаря · Отправка действий отключена',
  publicBanner: 'Публичные источники, учебные данные и ручной импорт личного календаря. Отправка действий отключена.',
  bannerNote: 'Статусы сохраняются локально. Ничего не отправляется. После обновления страницы потребуется войти заново.',
  loginTitle: 'Личное пространство', loginHint: 'Войди с паролем владельца, который был создан на этом сервере.',
  ownerPassword: 'Пароль владельца', signIn: 'Войти',
  workspace: 'РАБОЧЕЕ ПРОСТРАНСТВО', headline1: 'Всё в одном месте.', headline2: 'Всё по полочкам.',
  service: 'Сервис', account: 'Аккаунт', workflowStatus: 'Статус',
  allStatuses: 'Все статусы', allServices: 'Все сервисы', allAccounts: 'Все аккаунты',
  collect: 'Собрать события', collectHint: 'Загружает одну страницу событий для выбранного аккаунта или для всех аккаунтов, если ничего не выбрано.',
  logout: 'Выйти', overview: 'ОБЗОР СОБЫТИЙ', inbox: 'Входящие', search: 'Поиск событий',
  searchPlaceholder: 'Поиск по темам, содержимому и идентификаторам…', detailsAria: 'Подробности выбранного события',
  itemDetails: 'Подробности', selectPrompt: 'Выбери событие, чтобы изменить его статус.',
  footer: 'Предварительная версия · Только localhost · Личный календарь через ручной импорт · Без отправки действий',
  noscript: 'Для работы этой локальной панели требуется JavaScript.',
  detailStatus: 'Статус (только в интерфейсе)', save: 'Сохранить статус',
  saved: 'Статус сохранён локально. Никаких действий не отправлено.',
  itemCount: 'Событий: {count}',
  empty: 'Ничего не найдено. Загрузи события, чтобы наполнить список.',
  signedIn: 'Вход выполнен. Сбор данных запускается вручную и доступен только для чтения.',
  collected: 'События собраны. Повторный сбор не создаёт дубли, но публичные данные могут обновляться.',
  loggedOut: 'Выход выполнен. Сессия закрыта.',
  requestFailed: 'Ошибка запроса. Используй точный адрес localhost и при необходимости войди снова.',
  calendarEyebrow: 'ЛИЧНОЕ РАСПИСАНИЕ',
  calendarTitle: 'Занятия по неделям',
  calendarHint: 'Экспортируй одну неделю в iCal (.ics) и загрузи файл сюда. Запросов к сайту университета не будет.',
  calendarFile: 'Файл iCalendar (.ics)', calendarImport: 'Импортировать неделю',
  calendarWeek: 'Неделя с', calendarNone: 'Пока не загружено ни одной недели.',
  calendarNoClasses: 'Занятий нет', calendarUpdated: 'Последнее обновление календаря: {date} UTC',
  calendarSaved: 'Загружено занятий: {count}; изменено: {changed}, удалено: {removed}.',
  calendarBadFile: 'Выбери файл .ics размером не более 96 КиБ.',
  languageAria: 'Язык интерфейса',
  'status.new': 'Новые', 'status.review': 'На рассмотрении', 'status.deferred': 'Отложенные', 'status.done': 'Готово',
};
export function normalizeLocale(locale) { return LOCALES.includes(locale) ? locale : 'en'; }
export function t(locale, key, params = {}) {
  const message = (normalizeLocale(locale) === 'ru' ? ru : en)[key] ?? en[key] ?? key;
  return message.replace(/\{([a-z]+)\}/g, (_, name) => String(params[name] ?? ''));
}
export function formatDate(timestamp, locale) {
  const date = new Date(timestamp);
  return Number.isNaN(date.valueOf()) ? timestamp : new Intl.DateTimeFormat(
    normalizeLocale(locale) === 'ru' ? 'ru-RU' : 'en-US',
    { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' },
  ).format(date) + ' UTC';
}
