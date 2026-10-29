export const labels = {
  ko: {
    subtitle: '읽기 쉬운 작업 운영 보드', boardDescription: 'Hermes CLI와 같은 DB를 사용하는 전용 칸반 WebUI', newBoard: '보드 추가', refresh: '새로고침', themeDark: '다크로 전환', themeLight: '라이트로 전환', quickTitle: '작업 제목을 입력하고 Enter',
    taskCreate: 'Task 추가', taskCreateHint: '필요할 때만 제목, 설명, 담당 프로필, 상태를 입력해 새 task를 생성합니다.', taskTitlePlaceholder: '작업 제목', taskBodyPlaceholder: '작업 설명/지시사항(선택)',
    assignee: '담당 프로필', create: '추가', created: '생성일', createdToast: '생성됨', search: '작업 제목/내용/ID 검색', allAssignees: '전체 담당자', unassigned: '미지정', profileMissing: '담당 프로필 미지정', profileMissingShort: '프로필 필요', agentProfile: '프로필', manualAssignee: '수동', showArchived: '보관함 표시',
    bulkCreate: '일괄 추가', boardName: '보드 이름', description: '설명', cancel: '취소', bulkHint: '한 줄에 작업 하나씩 입력하세요.', loading: '불러오는 중…',
    workflow: 'Workflow', workflowCreate: 'AI Workflow 생성', workflowDesignerHint: '프롬프트와 첨부파일로 작업 DAG를 설계한 뒤 승인 시 실제 Kanban task로 적용합니다.', workflowPrompt: 'Workflow 프롬프트', workflowPromptPlaceholder: '목표, 산출물, 제약, 원하는 단계 수를 설명하세요', workflowPlannerProfile: 'Planner 프로필', workflowAttachments: '첨부파일', workflowPlan: '설계', workflowPlanning: 'AI가 workflow 초안을 설계하는 중…', workflowRevise: '수정', workflowRevisionPlaceholder: '변경할 단계/담당 프로필/의존성을 설명하세요', workflowApply: '적용', workflowDraftStatus: 'Draft 상태', workflowDraftEmpty: '프롬프트를 입력하고 설계를 누르면 초안이 표시됩니다.', workflowNotApplyable: '아직 적용할 수 없는 초안입니다. 질문을 해결한 뒤 수정 요청을 보내세요.', workflowInstance: 'Instance ID', workflowStep: '현재 단계', workflowSteps: '단계',
    updateAvailable: '새 업데이트 사용 가능', updateTitle: 'KanbanWebUI 업데이트', updateApply: '업데이트 후 재시작', updateLater: '나중에', updateChecking: '업데이트 상태 확인 중…', updateRestarting: '업데이트 적용 중… 서버가 재시작되면 자동으로 새로고침합니다.', updateBlocked: '자동 업데이트 불가', updateNoCommits: '커밋 목록 없음',
    triage: '분류', todo: '대기', ready: '준비', running: '실행중', blocked: '막힘', done: '완료', archived: '보관',
    title: '제목', body: '본문', noDescription: '설명 없음', priority: '우선순위', status: '상태', workspace: '워크스페이스', createdBy: '생성자',
    comments: '댓글', events: '이벤트', runs: '런', monitor: 'Live Run Monitor', context: '컨텍스트', log: '로그', workerLog: 'Worker 로그',
    dependencies: '의존성', parents: '부모', children: '자식', parent: '부모', child: '자식', chooseTask: '작업 선택', none: '없음', remove: '삭제',
    parentPortHint: '왼쪽 부모 포트: 다른 task의 오른쪽 자식 포트로 드래그해 부모로 연결', childPortHint: '오른쪽 자식 포트: 다른 task의 왼쪽 부모 포트로 드래그해 자식으로 연결', linkCreatedToast: '부모/자식 연결됨', linkInvalidToast: '왼쪽 부모 포트와 오른쪽 자식 포트만 연결할 수 있습니다.', linkSameTaskToast: '같은 task끼리는 연결할 수 없습니다.',
    dependencyViewFocus: '관계선: 선택 중심', dependencyViewAll: '관계선: 전체', dependencyViewBlocked: '관계선: 막힘', dependencyViewOff: '관계선: 숨김',
    dependencyMap: '관계 지도', currentTask: '현재 작업', noDependencies: '연결된 부모/자식 없음',
    notifyHomeChannels: '홈 채널 알림', noHomeChannels: '설정된 홈 채널 없음', noWorkerLog: 'worker 로그 없음',
    complete: '완료', block: '막기', unblock: '해제', archive: '보관', save: '저장', close: '닫기', addComment: '댓글 추가',
    operations: 'Operations', opsOverview: 'Operations 개요', opsRunning: '실행 중', opsHeartbeatOverdue: 'Heartbeat 지연', opsRetryQueue: 'Retry queue', opsBlockedAfterRetries: '재시도 후 막힘', opsRecentFailures: '최근 실패', opsNoRunning: '실행 중인 작업 없음', opsNoRetry: '재시도 후보 없음', opsNoBlockedAfterRetries: '재시도 후 막힌 작업 없음', opsNoFailures: '최근 실패 이벤트 없음', opsEligibleNow: '지금 가능', opsEstimatedWait: '예상 대기', opsAttempt: '시도', opsLastError: '마지막 오류', opsOpenTask: '열기', opsEstimatedBackoffAdvisory: '표시된 backoff는 현재 실패 정보로 계산한 참고용 추정치이며 dispatcher가 아직 강제하지 않습니다.', empty: '없음'
  },
  en: {
    subtitle: 'Readable operations board', boardDescription: 'Dedicated WebUI over the same DB the Hermes CLI uses', newBoard: 'New board', refresh: 'Refresh', themeDark: 'Switch dark', themeLight: 'Switch light', quickTitle: 'Type a task title and press Enter',
    taskCreate: 'Create task', taskCreateHint: 'Open this dialog only when you need to set title, details, agent profile, and status for a new task.', taskTitlePlaceholder: 'Task title', taskBodyPlaceholder: 'Task details/instructions (optional)',
    assignee: 'Agent profile', create: 'Create', created: 'Created', createdToast: 'Created', search: 'Search title/body/ID', allAssignees: 'All assignees', unassigned: 'Unassigned', profileMissing: 'Agent profile missing', profileMissingShort: 'Needs profile', agentProfile: 'profile', manualAssignee: 'manual', showArchived: 'Show archived',
    bulkCreate: 'Bulk create', boardName: 'Board name', description: 'Description', cancel: 'Cancel', bulkHint: 'One task per line.', loading: 'Loading…',
    workflow: 'Workflow', workflowCreate: 'Create AI workflow', workflowDesignerHint: 'Design a task DAG from a prompt and attachments, then approve it into real Kanban tasks.', workflowPrompt: 'Workflow prompt', workflowPromptPlaceholder: 'Describe goals, outputs, constraints, and desired step count', workflowPlannerProfile: 'Planner profile', workflowAttachments: 'Attachments', workflowPlan: 'Plan', workflowPlanning: 'AI is designing a workflow draft…', workflowRevise: 'Revise', workflowRevisionPlaceholder: 'Describe step/profile/dependency changes', workflowApply: 'Apply', workflowDraftStatus: 'Draft status', workflowDraftEmpty: 'Enter a prompt and click Plan to preview a draft.', workflowNotApplyable: 'This draft is not applyable yet. Resolve questions and send a revision.', workflowInstance: 'Instance ID', workflowStep: 'Current step', workflowSteps: 'steps',
    updateAvailable: 'Update available', updateTitle: 'KanbanWebUI update', updateApply: 'Update and restart', updateLater: 'Later', updateChecking: 'Checking update status…', updateRestarting: 'Applying update… this page will reload after the server restarts.', updateBlocked: 'Automatic update blocked', updateNoCommits: 'No commit details',
    triage: 'Triage', todo: 'Todo', ready: 'Ready', running: 'Running', blocked: 'Blocked', done: 'Done', archived: 'Archived',
    title: 'Title', body: 'Body', noDescription: 'No description', priority: 'Priority', status: 'Status', workspace: 'Workspace', createdBy: 'Created by',
    comments: 'Comments', events: 'Events', runs: 'Runs', monitor: 'Live Run Monitor', context: 'Context', log: 'Log', workerLog: 'Worker log',
    dependencies: 'Dependencies', parents: 'Parents', children: 'Children', parent: 'Parent', child: 'Child', chooseTask: 'Choose task', none: 'None', remove: 'Remove',
    parentPortHint: 'Left parent port: drag to another task right child port to link as parent', childPortHint: 'Right child port: drag to another task left parent port to link as child', linkCreatedToast: 'Parent/child linked', linkInvalidToast: 'Connect one left parent port with one right child port.', linkSameTaskToast: 'A task cannot link to itself.',
    dependencyViewFocus: 'Lines: Focus', dependencyViewAll: 'Lines: All', dependencyViewBlocked: 'Lines: Blocked', dependencyViewOff: 'Lines: Hidden',
    dependencyMap: 'Dependency map', currentTask: 'Current task', noDependencies: 'No parent/child links',
    notifyHomeChannels: 'Notify home channels', noHomeChannels: 'No home channels configured', noWorkerLog: 'No worker log yet',
    complete: 'Complete', block: 'Block', unblock: 'Unblock', archive: 'Archive', save: 'Save', close: 'Close', addComment: 'Add comment',
    operations: 'Operations', opsOverview: 'Operations overview', opsRunning: 'Running now', opsHeartbeatOverdue: 'Heartbeat overdue', opsRetryQueue: 'Retry queue', opsBlockedAfterRetries: 'Blocked after retries', opsRecentFailures: 'Recent failures', opsNoRunning: 'No running tasks', opsNoRetry: 'No retry candidates', opsNoBlockedAfterRetries: 'No tasks blocked after retries', opsNoFailures: 'No recent failure events', opsEligibleNow: 'Eligible now', opsEstimatedWait: 'Estimated wait', opsAttempt: 'Attempt', opsLastError: 'Last error', opsOpenTask: 'Open task', opsEstimatedBackoffAdvisory: 'Estimated backoff is advisory until dispatcher-level backoff is implemented.', empty: 'None'
  },
  ru: {
    subtitle: 'Доска исполнения задач', boardDescription: 'Отдельный интерфейс к той же базе, что и Hermes CLI', newBoard: 'Новая доска', refresh: 'Обновить', themeDark: 'Тёмная тема', themeLight: 'Светлая тема', quickTitle: 'Введите название задачи и нажмите Enter',
    taskCreate: 'Создать задачу', taskCreateHint: 'Открывайте это окно, только когда нужно задать заголовок, описание, профиль агента и статус новой задачи.', taskTitlePlaceholder: 'Название задачи', taskBodyPlaceholder: 'Описание задачи / инструкции (необязательно)',
    assignee: 'Профиль агента', create: 'Создать', created: 'Создано', createdToast: 'Создано', search: 'Поиск по названию, тексту, ID', allAssignees: 'Все исполнители', unassigned: 'Не назначен', profileMissing: 'Профиль агента не задан', profileMissingShort: 'Нужен профиль', agentProfile: 'профиль', manualAssignee: 'вручную', showArchived: 'Показывать архив',
    bulkCreate: 'Массовое создание', boardName: 'Название доски', description: 'Описание', cancel: 'Отмена', bulkHint: 'По одной задаче в строке.', loading: 'Загрузка…',
    workflow: 'Workflow', workflowCreate: 'Создать AI workflow', workflowDesignerHint: 'Спроектируйте граф задач из промпта и вложений, затем примените его как настоящие карточки.', workflowPrompt: 'Промпт workflow', workflowPromptPlaceholder: 'Опишите цели, результаты, ограничения и желаемое число шагов', workflowPlannerProfile: 'Профиль планировщика', workflowAttachments: 'Вложения', workflowPlan: 'Спроектировать', workflowPlanning: 'AI проектирует черновик workflow…', workflowRevise: 'Исправить', workflowRevisionPlaceholder: 'Опишите изменения шагов, профилей или зависимостей', workflowApply: 'Применить', workflowDraftStatus: 'Статус черновика', workflowDraftEmpty: 'Введите промпт и нажмите «Спроектировать», чтобы увидеть черновик.', workflowNotApplyable: 'Этот черновик пока нельзя применить. Ответьте на вопросы и отправьте правки.', workflowInstance: 'ID экземпляра', workflowStep: 'Текущий шаг', workflowSteps: 'шагов',
    updateAvailable: 'Доступно обновление', updateTitle: 'Обновление KanbanWebUI', updateApply: 'Обновить и перезапустить', updateLater: 'Позже', updateChecking: 'Проверка обновлений…', updateRestarting: 'Применяю обновление… страница перезагрузится после перезапуска сервера.', updateBlocked: 'Автообновление недоступно', updateNoCommits: 'Нет списка коммитов',
    triage: 'Разбор', todo: 'Ожидают', ready: 'Готовы', running: 'В работе', blocked: 'Заблокированы', done: 'Готово', archived: 'Архив',
    title: 'Заголовок', body: 'Текст', noDescription: 'Без описания', priority: 'Приоритет', status: 'Статус', workspace: 'Рабочий каталог', createdBy: 'Создал',
    comments: 'Комментарии', events: 'События', runs: 'Прогоны', monitor: 'Монитор прогона', context: 'Контекст', log: 'Лог', workerLog: 'Лог воркера',
    dependencies: 'Зависимости', parents: 'Родители', children: 'Дети', parent: 'Родитель', child: 'Ребёнок', chooseTask: 'Выберите задачу', none: 'Нет', remove: 'Удалить',
    parentPortHint: 'Левый порт родителя: перетащите на правый порт ребёнка другой задачи, чтобы сделать её родителем', childPortHint: 'Правый порт ребёнка: перетащите на левый порт родителя другой задачи, чтобы сделать её ребёнком', linkCreatedToast: 'Связь родитель/ребёнок создана', linkInvalidToast: 'Соединяйте только левый порт родителя с правым портом ребёнка.', linkSameTaskToast: 'Задача не может ссылаться на себя.',
    dependencyViewFocus: 'Связи: от выбранной', dependencyViewAll: 'Связи: все', dependencyViewBlocked: 'Связи: блокировки', dependencyViewOff: 'Связи: скрыты',
    dependencyMap: 'Карта связей', currentTask: 'Текущая задача', noDependencies: 'Нет связей родитель/ребёнок',
    notifyHomeChannels: 'Уведомлять домашние каналы', noHomeChannels: 'Домашние каналы не настроены', noWorkerLog: 'Лога воркера ещё нет',
    complete: 'Завершить', block: 'Заблокировать', unblock: 'Разблокировать', archive: 'В архив', save: 'Сохранить', close: 'Закрыть', addComment: 'Добавить комментарий',
    operations: 'Operations', opsOverview: 'Сводка Operations', opsRunning: 'Сейчас в работе', opsHeartbeatOverdue: 'Просрочен heartbeat', opsRetryQueue: 'Очередь повторов', opsBlockedAfterRetries: 'Заблокированы после повторов', opsRecentFailures: 'Последние сбои', opsNoRunning: 'Нет задач в работе', opsNoRetry: 'Нет кандидатов на повтор', opsNoBlockedAfterRetries: 'Нет задач, заблокированных после повторов', opsNoFailures: 'Нет свежих событий сбоя', opsEligibleNow: 'Можно сейчас', opsEstimatedWait: 'Ожидание', opsAttempt: 'Попытка', opsLastError: 'Последняя ошибка', opsOpenTask: 'Открыть', opsEstimatedBackoffAdvisory: 'Показанная задержка — расчётная оценка по текущим ошибкам; диспетчер её пока не соблюдает.', empty: 'Нет'
  }
};

const LANGS = ['ru', 'en', 'ko'];
const stored = localStorage.getItem('kanbanLang');
let currentLang = LANGS.includes(stored) ? stored : 'ru';

export function lang() { return currentLang; }
export function setLang(next) {
  currentLang = LANGS.includes(next) ? next : 'ru';
  localStorage.setItem('kanbanLang', currentLang);
  applyI18n();
}
export function nextLang() { return LANGS[(LANGS.indexOf(currentLang) + 1) % LANGS.length]; }
export function t(key) { return (labels[currentLang] && labels[currentLang][key]) || labels.en[key] || key; }

export function applyI18n(root = document) {
  root.documentElement?.setAttribute('lang', currentLang);
  root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  const toggle = root.getElementById?.('langToggle');
  if (toggle) toggle.textContent = nextLang().toUpperCase();
}
