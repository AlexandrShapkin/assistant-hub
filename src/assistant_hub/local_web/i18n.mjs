// User-interface language is deliberately ephemeral; authentication state remains separate.
export const DEFAULT_LOCALE = 'ru';
export const LOCALES = Object.freeze(['ru', 'en']);
const en = {
  pageTitle: 'Assistant Hub · Local workspace',
  localWorkspace: 'LOCAL WORKSPACE',
  syntheticBanner: 'Synthetic demo — synthetic-only; no real sources linked',
  publicBanner: 'Public read-only sources and synthetic fixtures — no private accounts or outgoing actions.',
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
  footer: 'Pre-alpha · Localhost only · Public or synthetic data · No dispatch',
  noscript: 'JavaScript modules are required for this local application.',
  detailStatus: 'Workflow status (UI only)', save: 'Save status',
  saved: 'Workflow status saved locally. No action dispatched.',
  itemCount: '{count} items',
  empty: 'No matching items. Collect events to populate the inbox.',
  signedIn: 'Signed in. Collection is read-only and manual.',
  collected: 'Page collected. Repeated collection deduplicates; public snapshots can miss updates.',
  loggedOut: 'Logged out. Session revoked.',
  requestFailed: 'Request failed. Use the exact localhost URL and sign in again if needed.',
  languageAria: 'Interface language',
  'status.new': 'New', 'status.review': 'Review', 'status.deferred': 'Deferred', 'status.done': 'Done',
};
const ru = {
  pageTitle: 'Assistant Hub · Личное пространство',
  localWorkspace: 'ЛИЧНОЕ ПРОСТРАНСТВО',
  syntheticBanner: 'Учебная демонстрация — реальные источники не подключены',
  publicBanner: 'Публичные источники доступны только для чтения и дополнены учебными данными. Нет доступа к приватным аккаунтам или отправке действий.',
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
  footer: 'Предварительная версия · Только localhost · Публичные или учебные данные · Без отправки действий',
  noscript: 'Для работы этой локальной панели требуется JavaScript.',
  detailStatus: 'Статус (только в интерфейсе)', save: 'Сохранить статус',
  saved: 'Статус сохранён локально. Никаких действий не отправлено.',
  itemCount: 'Событий: {count}',
  empty: 'Ничего не найдено. Загрузи события, чтобы наполнить список.',
  signedIn: 'Вход выполнен. Сбор данных запускается вручную и доступен только для чтения.',
  collected: 'События собраны. Повторный сбор не создаёт дубли, но публичные данные могут обновляться.',
  loggedOut: 'Выход выполнен. Сессия закрыта.',
  requestFailed: 'Ошибка запроса. Используй точный адрес localhost и при необходимости войди снова.',
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
