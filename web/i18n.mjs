// Presentation-only translations. No browser storage, network or provider schema changes.
export const DEFAULT_LOCALE = 'ru';
export const LOCALES = Object.freeze(['ru', 'en']);
const en = {
  pageTitle: 'Assistant Hub · Offline preview', skip: 'Skip to inbox', preview: 'OFFLINE PREVIEW',
  about: 'About this demo ↗', demo: 'Synthetic demo — no accounts connected',
  demoNotice: 'All activity is invented. Changes stay in memory and reset on refresh.',
  filters: 'Sources and filters', workspace: 'YOUR WORKSPACE', headline1: 'One place.',
  headline2: 'A clearer picture.', intro: 'A quiet overview of activity across your tools.',
  inboxGroup: 'INBOX', reset: 'Reset filters', servicesGroup: 'SERVICES',
  accountsGroup: 'ACCOUNTS', fictional: 'sample only', sidebarNote: 'Built around your context',
  sidebarNoteText: 'Service and account identities travel with every item. No tools are connected in this preview.',
  overview: 'ACTIVITY OVERVIEW', inbox: 'Inbox', sampleDate: 'Sample day · 14 Oct 2026',
  search: 'Search activity', searchPlaceholder: 'Search titles, content, services…',
  priority: 'Priority', allPriorities: 'All priorities', important: 'Important', normal: 'Normal',
  sort: 'Sort', latest: 'Latest first', importantFirst: 'Important first',
  activityItems: 'Activity items', detailsLabel: 'Selected item details',
  footer: 'Offline by design · Synthetic data only · No authentication, connected accounts, or dispatch',
  noscript: 'This offline preview requires JavaScript modules. No accounts or private data are available.',
  allActivity: 'All activity', allServices: 'All services', allAccounts: 'All accounts',
  results: '{visible} of {total} synthetic items', emptyTitle: 'A little quieter here.',
  emptyText: 'No matching items. Try another search or reset the filters.',
  nothingSelected: 'Nothing selected', selectItem: 'Choose an item from the current results.',
  itemDetails: 'ITEM DETAILS', metadataStatus: 'Status', metadataPriority: 'Priority',
  metadataKind: 'Kind', metadataId: 'Sample ID', organize: 'Organize this item',
  markDone: 'Mark done', defer: 'Defer', markReview: 'Mark for review', reopen: 'Reopen',
  simulationHeading: 'ACTION SIMULATION', simulationExplainer: 'Practice the review flow. This does not grant permission, send a message, or run an action.',
  simulationState: 'Simulation state: {state}',
  simulationDraft: 'Synthetic draft: {action}. Gather context and prepare a short note for discussion.',
  simulationButtonDraft: 'Simulate draft', simulationButtonReview: 'Request review · simulation',
  simulationButtonApprove: 'Approve · simulation', simulationButtonReject: 'Reject · simulation',
  simulationNotice: 'Simulation only: {operation}. Nothing was sent or executed.',
  simulationDenied: 'This simulation step is unavailable. Complete the previous review step first.',
  detailFoot: 'Synthetic content · In-memory changes only', language: 'Interface language',
  'source.communication': 'Communication', 'source.git': 'Git activity',
  'source.website': 'Website updates', 'source.device': 'Device health',
  'status.new': 'New', 'status.review': 'Review', 'status.deferred': 'Deferred', 'status.done': 'Done',
  'kind.message': 'Message', 'kind.review': 'Review', 'kind.health': 'Health',
  'kind.update': 'Update', 'kind.activity': 'Activity',
  'simulation.draft': 'Draft', 'simulation.requested': 'Review requested',
  'simulation.approved': 'Approved', 'simulation.rejected': 'Rejected',
  'operation.done': 'marked done', 'operation.deferred': 'deferred',
  'operation.review': 'marked for review', 'operation.new': 'reopened',
  'operation.draft': 'draft created', 'operation.request-review': 'review requested',
  'operation.approve': 'approved', 'operation.reject': 'rejected',
};
const ru = {
  pageTitle: 'Assistant Hub · Демонстрация', skip: 'К списку событий', preview: 'АВТОНОМНАЯ ДЕМО-ВЕРСИЯ',
  about: 'О демонстрации ↗', demo: 'Учебные данные — аккаунты не подключены',
  demoNotice: 'Все события вымышлены. Изменения хранятся в памяти и исчезают при обновлении страницы.',
  filters: 'Источники и фильтры', workspace: 'РАБОЧЕЕ ПРОСТРАНСТВО', headline1: 'Всё в одном месте.',
  headline2: 'Всё по полочкам.', intro: 'Спокойный обзор событий из разных инструментов.',
  inboxGroup: 'ВХОДЯЩИЕ', reset: 'Сбросить фильтры', servicesGroup: 'СЕРВИСЫ',
  accountsGroup: 'АККАУНТЫ', fictional: 'вымышленные', sidebarNote: 'Контекст важен',
  sidebarNoteText: 'У каждого события сохраняется связь с сервисом и аккаунтом. В этой версии реальные сервисы не подключены.',
  overview: 'ОБЗОР СОБЫТИЙ', inbox: 'Входящие', sampleDate: 'Пример дня · 14 октября 2026',
  search: 'Поиск событий', searchPlaceholder: 'Поиск по темам, содержимому и сервисам…',
  priority: 'Приоритет', allPriorities: 'Все приоритеты', important: 'Важный', normal: 'Обычный',
  sort: 'Сортировка', latest: 'Сначала новые', importantFirst: 'Сначала важные',
  activityItems: 'Список событий', detailsLabel: 'Подробности выбранного события',
  footer: 'Автономная демо-версия · Только вымышленные данные · Нет авторизации, аккаунтов и отправки действий',
  noscript: 'Для этой демо-версии нужен JavaScript. Реальные аккаунты и личные данные недоступны.',
  allActivity: 'Все события', allServices: 'Все сервисы', allAccounts: 'Все аккаунты',
  results: '{visible} из {total} учебных событий', emptyTitle: 'Здесь пока пусто.',
  emptyText: 'Ничего не найдено. Измени запрос или сбрось фильтры.',
  nothingSelected: 'Ничего не выбрано', selectItem: 'Выбери событие из результатов.',
  itemDetails: 'ПОДРОБНОСТИ', metadataStatus: 'Статус', metadataPriority: 'Приоритет',
  metadataKind: 'Тип', metadataId: 'Учебный ID', organize: 'Работа с событием',
  markDone: 'Завершить', defer: 'Отложить', markReview: 'На рассмотрение', reopen: 'Вернуть в новые',
  simulationHeading: 'ИМИТАЦИЯ ДЕЙСТВИЯ', simulationExplainer: 'Это тренировка процесса согласования. Никаких разрешений, сообщений или реальных действий.',
  simulationState: 'Состояние имитации: {state}',
  simulationDraft: 'Учебный черновик: {action}. Уточни контекст и подготовь короткую заметку для обсуждения.',
  simulationButtonDraft: 'Создать учебный черновик', simulationButtonReview: 'Запросить проверку · имитация',
  simulationButtonApprove: 'Одобрить · имитация', simulationButtonReject: 'Отклонить · имитация',
  simulationNotice: 'Только имитация: {operation}. Ничего не отправлено и не выполнено.',
  simulationDenied: 'Сейчас действие недоступно. Сначала заверши предыдущий шаг согласования.',
  detailFoot: 'Вымышленные данные · Изменения только в памяти', language: 'Язык интерфейса',
  'source.communication': 'Сообщения', 'source.git': 'Разработка',
  'source.website': 'Сайты', 'source.device': 'Устройства',
  'status.new': 'Новые', 'status.review': 'На рассмотрении', 'status.deferred': 'Отложенные', 'status.done': 'Готово',
  'kind.message': 'Сообщение', 'kind.review': 'Проверка', 'kind.health': 'Состояние',
  'kind.update': 'Обновление', 'kind.activity': 'Активность',
  'simulation.draft': 'Черновик', 'simulation.requested': 'Проверка запрошена',
  'simulation.approved': 'Одобрено', 'simulation.rejected': 'Отклонено',
  'operation.done': 'завершено', 'operation.deferred': 'отложено',
  'operation.review': 'отправлено на рассмотрение', 'operation.new': 'возвращено в новые',
  'operation.draft': 'черновик создан', 'operation.request-review': 'запрошена проверка',
  'operation.approve': 'одобрено', 'operation.reject': 'отклонено',
};
export function normalizeLocale(locale) { return LOCALES.includes(locale) ? locale : 'en'; }
export function t(locale, key, params = {}) {
  const text = (normalizeLocale(locale) === 'ru' ? ru : en)[key] ?? en[key] ?? key;
  return text.replace(/\{([a-z]+)\}/g, (_, name) => String(params[name] ?? ''));
}
export function formatTime(timestamp, locale) {
  return new Intl.DateTimeFormat(normalizeLocale(locale) === 'ru' ? 'ru-RU' : 'en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
  }).format(new Date(timestamp)) + ' UTC';
}
const russianAccounts = {
  'Studio · demo': 'Студия · пример', 'Workshop · demo': 'Мастерская · пример',
  'Lab · demo': 'Лаборатория · пример', 'Reading · demo': 'Чтение · пример',
  'Community · demo': 'Сообщество · пример', 'Sandbox · demo': 'Песочница · пример',
};
export const accountLabel = (account, locale) =>
  normalizeLocale(locale) === 'ru' ? (russianAccounts[account] ?? account) : account;

// UI-only Russian fixture texts. Never change source/account/ID or backend event fields.
const russianFixtures = [
  ['Уточнения к следующему этапу', 'Мира из вымышленной дизайн-группы задала три вопроса перед проверкой.', 'Группа хочет согласовать объём, сроки и ответственного за прототип. Это выдуманная переписка.', 'Подготовить черновик ответа'],
  ['Изменения навигации готовы к проверке', 'Вымышленный набор изменений улучшает управление с клавиатуры.', 'Набор изменений 42 уточняет подписи и видимость фокуса. События репозитория придуманы.', 'Подготовить заметки к проверке'],
  ['На учебном устройстве заканчивается место', 'Воображаемое устройство показывает 82 % занятого диска.', 'Это учебный показатель. Настоящие устройства не проверяются и не контролируются.', 'Составить план обслуживания'],
  ['Заметки о спокойных интерфейсах', 'Вымышленное издание опубликовало статью о простом дизайне.', 'Пример посвящён группировке данных и понятным следующим шагам.', null],
  ['Заметки из сообщества', 'Роуэн прислал вымышленный итог еженедельной встречи.', 'Обсуждались небольшие прототипы, полезная обратная связь и эксперименты.', 'Подготовить черновик ответа'],
  ['Обновлены примеры документации', 'В вымышленной документации появились более понятные примеры.', 'Учебный проект объясняет настройку и ожидаемый результат.', null],
  ['Новая глава в библиотеке шаблонов', 'Выдуманное обновление предлагает компоновку для небольших экранов.', 'Глава о гибких колонках, удобной ширине текста и видимом фокусе.', null],
  ['Еженедельная проверка без отклонений', 'Воображаемая тестовая станция завершила учебную проверку.', 'Температура, диск и очередь задач вымышлены. Диагностика не запускалась.', null],
  ['Новое время встречи по концепции', 'Вымышленная команда предложила перенести встречу.', 'План: сравнить два эскиза и выбрать один вопрос для следующего исследования.', 'Подготовить заметку о времени'],
  ['Открыта ветка прототипа', 'В учебном проекте появилась экспериментальная ветка.', 'Это вымышленная ветка для компактной панели настроек. Настоящий репозиторий не подключён.', null],
  ['Готова подборка материалов за месяц', 'В список добавлены пять вымышленных рекомендаций для чтения.', 'Учебная подборка о доступных формах, разумных настройках и поддержке систем.', null],
  ['Записаны учебные данные батареи', 'Вымышленное переносное устройство сообщает о стабильном заряде.', 'Это статический образец, не телеметрия. Адреса и идентификаторы устройств отсутствуют.', null],
];
export function presentEvent(event, locale) {
  if (normalizeLocale(locale) !== 'ru') return event;
  const match = /^sample-(\d+)$/.exec(event.id);
  const index = match ? Number(match[1]) - 1 : -1;
  const translated = russianFixtures[index];
  return translated ? { ...event, title: translated[0], summary: translated[1],
    body: translated[2], ...(translated[3] ? { proposedAction: translated[3] } : {}) } : event;
}
