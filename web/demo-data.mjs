// Entirely invented fixtures. No adapter, account access or backend connection.
const examples = [
  ['communication', 'Studio · demo', 'message', 'A little clarity for the next milestone', 'Mira from the fictional design circle shared three questions for the next review.', 'The group would like to agree on scope, timing, and who will prepare the prototype. This is an invented conversation.', 'important', 'review', 'Prepare a reply draft'],
  ['git', 'Workshop · demo', 'review', 'Navigation refinements ready for review', 'A fictional change set improves keyboard navigation and empty states.', 'Change set 42 includes focus styles and clearer labels. All repository activity here is fabricated.', 'important', 'review', 'Prepare review notes'],
  ['device', 'Lab · demo', 'health', 'Storage is approaching its demo threshold', 'The imaginary bench device reports 82% storage usage.', 'Synthetic health sample only. No device is being monitored, accessed, or controlled.', 'important', 'new', 'Draft a maintenance checklist'],
  ['website', 'Reading · demo', 'update', 'Field notes: designing for quiet focus', 'A fictional publication added an essay about calm interfaces.', 'The example article explores grouping related information and keeping the next step clear.', 'normal', 'new', null],
  ['communication', 'Community · demo', 'message', 'Notes from the maker circle', 'Rowan shared a synthetic recap of the weekly workshop.', 'Topics included small prototypes, useful feedback, and leaving space for experimentation.', 'normal', 'new', 'Prepare a reply draft'],
  ['git', 'Workshop · demo', 'activity', 'Documentation examples refreshed', 'An invented documentation update adds clearer setup examples.', 'The fictional project now explains its sample configuration and expected output.', 'normal', 'done', null],
  ['website', 'Studio · demo', 'update', 'The pattern library has a new chapter', 'A fabricated update introduces layouts for compact screens.', 'The chapter covers flexible columns, comfortable reading widths, and visible focus indicators.', 'normal', 'new', null],
  ['device', 'Lab · demo', 'health', 'Weekly health sample looks steady', 'The imaginary test station completed its synthetic check.', 'Temperature, storage, and task queue values are fictional. No diagnostics were run.', 'normal', 'done', null],
  ['communication', 'Studio · demo', 'message', 'A new time for the concept session', 'The fictional team suggested moving the concept session.', 'Suggested agenda: compare two sketches and choose one question to explore next.', 'normal', 'deferred', 'Draft a scheduling note'],
  ['git', 'Sandbox · demo', 'activity', 'Prototype branch opened', 'A synthetic project has a new experimental branch.', 'This invented branch explores a smaller settings panel. No remote repository is connected.', 'normal', 'new', null],
  ['website', 'Reading · demo', 'update', 'Monthly reading collection is ready', 'Five invented reading suggestions were added to the collection.', 'A synthetic digest covering accessible forms, useful defaults, and maintainable systems.', 'normal', 'deferred', null],
  ['device', 'Sandbox · demo', 'health', 'Demo battery sample recorded', 'The fictional portable test device reports a stable charge.', 'This is a static sample, not live telemetry. No device identity or address is included.', 'normal', 'new', null],
];
export const demoEvents = examples.map(([source, account, kind, title, summary, body, priority, status, action], index) => Object.freeze({
  id: `sample-${index + 1}`, source, account, kind, title, summary, body, priority, status,
  timestamp: new Date(Date.UTC(2026, 9, 14, 15, 45 - index * 17)).toISOString(),
  ...(action ? { proposedAction: action } : {}),
}));
