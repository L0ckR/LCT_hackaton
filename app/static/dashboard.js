const chartRegistry = {};
const pendingJobs = new Map();
const jobIndicator = document.getElementById('job-status');
const jobIndicatorMessage = document.getElementById('job-status-message');

let recentReviewsData = [];
let recentReviewsGrid = null;
const recentReviewsDom = {};
const RECENT_REVIEWS_LIMIT = 100;

let recentReviewsTotalCount = null;
let dashboardRefreshChain = Promise.resolve();

let resolveGridReady;
const gridReadyPromise = new Promise((resolve) => {
  resolveGridReady = resolve;
});

if (typeof window.gridjs !== 'undefined') {
  resolveGridReady();
} else {
  const gridScriptElement = document.getElementById('gridjs-script');
  if (gridScriptElement) {
    gridScriptElement.addEventListener('load', () => resolveGridReady(), { once: true });
    gridScriptElement.addEventListener(
      'error',
      () => {
        console.error('Failed to load Grid.js script');
        resolveGridReady();
      },
      { once: true },
    );
  } else {
    resolveGridReady();
  }
}

function whenGridReady(callback) {
  gridReadyPromise.then(() => {
    if (typeof window.gridjs === 'undefined') {
      console.error('Grid.js is not available');
      return;
    }
    try {
      callback();
    } catch (error) {
      console.error('Failed to render reviews table', error);
    }
  });
}

function showToast(message, variant = 'success') {
  if (!message) return;
  const toast = document.getElementById('toast');
  if (!toast) return;

  toast.classList.remove('hidden', 'toast-success', 'toast-error', 'show');
  toast.textContent = message;
  toast.classList.add(`toast-${variant}`);

  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  setTimeout(() => {
    toast.classList.remove('show');
    toast.classList.add('hidden');
  }, 4200);
}

function setJobMessage(message) {
  if (!jobIndicatorMessage) return;
  jobIndicatorMessage.textContent = message || 'Обработка…';
}

function showJobStatus(message) {
  if (!jobIndicator) return;
  if (message) {
    setJobMessage(message);
  }
  jobIndicator.classList.remove('hidden');
}

function hideJobStatus(force = false) {
  if (!jobIndicator) return;
  if (force || pendingJobs.size === 0) {
    jobIndicator.classList.add('hidden');
  }
}

function initFlashMessages() {
  const flashNode = document.getElementById('flash-data');
  if (!flashNode) return;
  const { status, error, job } = flashNode.dataset;
  if (job) {
    pendingJobs.set(job, { processed: 0, total: null });
    showJobStatus('Импорт запущен…');
  } else if (error) {
    showToast(error, 'error');
  } else if (status) {
    showToast(status, 'success');
  }

  if (status || error || job) {
    const url = new URL(window.location.href);
    url.searchParams.delete('status');
    url.searchParams.delete('error');
    url.searchParams.delete('job');
    const search = url.searchParams.toString();
    const cleaned = `${url.pathname}${search ? `?${search}` : ''}${url.hash}`;
    window.history.replaceState({}, '', cleaned);
  }
}

function attachJobStatusToForms(selector, message) {
  document.querySelectorAll(selector).forEach((form) => {
    form.addEventListener('submit', () => {
      showJobStatus(message);
    });
  });
}

function buildHeaders(authToken) {
  if (!authToken) {
    return {};
  }
  return {
    Authorization: `Bearer ${authToken}`,
  };
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = new Error(`Request failed: ${response.status}`);
    error.response = response;
    throw error;
  }
  return response.json();
}

function renderChart(card, labels, values, visualization, metric) {
  const widgetId = card.dataset.widgetId;
  const canvas = card.querySelector('.widget-chart');
  if (!canvas) return;

  const existingChart = chartRegistry[widgetId];
  if (existingChart) {
    existingChart.data.labels = labels;
    existingChart.data.datasets[0].data = values;
    existingChart.update();
    return;
  }

  const chartType = visualization === 'bar' ? 'bar' : 'line';
  card.classList.add('has-chart');
  canvas.height = 220;

  const chart = new Chart(canvas.getContext('2d'), {
    type: chartType,
    data: {
      labels,
      datasets: [
        {
          label: card.querySelector('h3')?.textContent || metric,
          data: values,
          fill: false,
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37, 99, 235, 0.3)',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false,
        },
      },
      scales: {
        y: {
          ticks: {
            precision: 2,
          },
        },
      },
    },
  });

  chartRegistry[widgetId] = chart;
}

async function loadWidgetChart(card, authToken) {
  const visualization = card.dataset.visualization;
  if (!visualization || visualization === 'metric') {
    return;
  }
  const widgetId = card.dataset.widgetId;
  const metric = card.dataset.metric;
  const canvas = card.querySelector('.widget-chart');
  if (!canvas) {
    return;
  }

  try {
    const payload = await fetchJson(`/dashboard/widgets/${widgetId}/timeseries`, {
      credentials: 'include',
      headers: buildHeaders(authToken),
      cache: 'no-store',
    });
    const data = Array.isArray(payload?.data) ? payload.data : [];
    const labels = data.map((item) => item.date);
    const values = data.map((item) => item.value);
    renderChart(card, labels, values, visualization, metric);
  } catch (error) {
    console.error('Failed to load widget chart', error);
    canvas.replaceWith('Unable to load chart');
  }
}

async function refreshAllCharts(authToken) {
  const cards = Array.from(document.querySelectorAll('.widget-card'));
  await Promise.all(cards.map((card) => loadWidgetChart(card, authToken)));
}

function formatMetricValue(value) {
  if (value === null || value === undefined) {
    return '—';
  }
  if (typeof value === 'number') {
    if (Number.isInteger(value)) {
      return value.toLocaleString('ru-RU');
    }
    return value.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
  }
  return String(value);
}

async function refreshWidgetCards(authToken) {
  try {
    const widgets = await fetchJson('/dashboard/widgets/', {
      credentials: 'include',
      headers: buildHeaders(authToken),
      cache: 'no-store',
    });
    if (!Array.isArray(widgets)) {
      return;
    }
    widgets.forEach((widget) => {
      const card = document.querySelector(
        `.widget-card[data-widget-id="${widget.id}"]`,
      );
      if (!card) return;

      if (widget.visualization === 'metric') {
        const valueNode = card.querySelector('.widget-value');
        if (valueNode) {
          valueNode.textContent = formatMetricValue(widget.value);
        }
      }

      if (widget.metric) {
        card.dataset.metric = widget.metric;
      }
      if (widget.visualization) {
        card.dataset.visualization = widget.visualization;
      }
    });
  } catch (error) {
    console.error('Failed to refresh widgets', error);
  }
}

async function refreshOverview(authToken) {
  try {
    const data = await fetchJson(`/analytics/overview?ts=${Date.now()}`, {
      credentials: 'include',
      headers: buildHeaders(authToken),
      cache: 'no-store',
    });

    const totalNode = document.getElementById('overview-total');
    const avgNode = document.getElementById('overview-average');
    if (totalNode) {
      totalNode.textContent = data.total_reviews ?? 0;
    }
    if (avgNode) {
      avgNode.textContent = (data.average_sentiment ?? 0).toFixed(2);
    }
    const list = document.getElementById('overview-highlights-list');
    const empty = document.getElementById('overview-highlights-empty');
    if (list) {
      list.innerHTML = '';
      const highlights = Array.isArray(data.highlights) ? data.highlights : [];
      if (highlights.length) {
        highlights.slice(0, 5).forEach((highlight) => {
          const li = document.createElement('li');
          li.textContent = highlight;
          list.appendChild(li);
        });
        list.classList.remove('hidden');
        if (empty) empty.classList.add('hidden');
      } else {
        list.classList.add('hidden');
        if (empty) empty.classList.remove('hidden');
      }
    }

    if (typeof data.total_reviews === 'number') {
      recentReviewsTotalCount = data.total_reviews;
      updateRecentReviewsMeta();
    }
  } catch (error) {
    console.error('Failed to refresh overview', error);
  }
}

function captureRecentReviewsDom() {
  recentReviewsDom.container = document.getElementById('recent-reviews-table');
  recentReviewsDom.empty = document.getElementById('recent-reviews-empty');
  recentReviewsDom.total = document.getElementById('recent-reviews-total');
}

function normalizeReview(review) {
  if (!review || typeof review !== 'object') {
    return null;
  }
  const id = Number.parseInt(review.id, 10);
  return {
    ...review,
    id: Number.isNaN(id) ? review.id : id,
    product: review.product ?? '',
    sentiment: review.sentiment ?? '',
    sentiment_score: review.sentiment_score,
    sentiment_summary: review.sentiment_summary ?? '',
    text: typeof review.text === 'string' ? review.text : review.text ?? '',
  };
}

function truncateText(value, limit = 120) {
  if (!value) return '—';
  const text = String(value);
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 1))}…`;
}

function formatReviewDate(value) {
  if (!value) return 'n/a';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'n/a';
  return date.toLocaleString();
}

function reviewToRow(review) {
  const score =
    typeof review.sentiment_score === 'number'
      ? review.sentiment_score.toFixed(2)
      : '—';

  return [
    review.id ?? '—',
    review.product || '—',
    review.sentiment || 'pending',
    score,
    formatReviewDate(review.date),
    truncateText(review.sentiment_summary, 90),
    truncateText(review.text, 160),
  ];
}

function updateRecentReviewsMeta() {
  if (recentReviewsDom.total) {
    const resolvedTotal =
      typeof recentReviewsTotalCount === 'number'
        ? recentReviewsTotalCount
        : recentReviewsData.length;
    recentReviewsDom.total.textContent = resolvedTotal ?? recentReviewsData.length ?? 0;
  }
  if (recentReviewsDom.empty) {
    if (recentReviewsData.length === 0) {
      recentReviewsDom.empty.classList.remove('hidden');
    } else {
      recentReviewsDom.empty.classList.add('hidden');
    }
  }
}

function renderRecentReviewsGrid() {
  updateRecentReviewsMeta();

  if (!recentReviewsDom.container) {
    return;
  }

  whenGridReady(() => {
    const data = recentReviewsData.map(reviewToRow);
    const config = {
      columns: [
        { id: 'id', name: 'ID' },
        { id: 'product', name: 'Product' },
        { id: 'sentiment', name: 'Sentiment' },
        { id: 'sentiment_score', name: 'Score' },
        { id: 'date', name: 'Date' },
        { id: 'sentiment_summary', name: 'Summary' },
        { id: 'text', name: 'Excerpt' },
      ],
      data,
      sort: true,
      search: {
        enabled: true,
        placeholder: 'Поиск отзывов…',
      },
      pagination: {
        enabled: true,
        limit: 10,
        summary: true,
      },
      className: {
        table: 'reviews',
      },
      language: {
        search: {
          placeholder: 'Поиск…',
        },
        pagination: {
          previous: 'Назад',
          next: 'Вперёд',
          showing: 'Показаны',
          results: 'записей',
        },
        noRecordsFound: 'Нет отзывов',
      },
    };

    if (!recentReviewsGrid) {
      recentReviewsDom.container.innerHTML = '';
      recentReviewsGrid = new gridjs.Grid(config);
      recentReviewsGrid.render(recentReviewsDom.container);
    } else {
      recentReviewsGrid.updateConfig({ data }).forceRender();
    }

    updateRecentReviewsMeta();
  });
}

function setRecentReviewsData(reviews) {
  recentReviewsData = Array.isArray(reviews)
    ? reviews
        .map((item) => normalizeReview(item))
        .filter(Boolean)
        .sort((a, b) => {
          const idA = typeof a.id === 'number' ? a.id : Number(a.id) || 0;
          const idB = typeof b.id === 'number' ? b.id : Number(b.id) || 0;
          return idB - idA;
        })
    : [];

  if (typeof recentReviewsTotalCount !== 'number') {
    recentReviewsTotalCount = recentReviewsData.length;
  }

  renderRecentReviewsGrid();
}

function hydrateRecentReviewsFromPayload() {
  const container = document.getElementById('recent-reviews-data');
  if (!container) return;
  try {
    const payload = JSON.parse(container.textContent || '[]');
    if (Array.isArray(payload)) {
      setRecentReviewsData(payload);
    }
  } catch (error) {
    console.error('Failed to parse initial recent reviews payload', error);
  } finally {
    container.remove();
  }
  updateRecentReviewsMeta();
}

async function refreshRecentReviews(authToken) {
  try {
    const data = await fetchJson(`/reviews/recent?limit=${RECENT_REVIEWS_LIMIT}&ts=${Date.now()}`, {
      credentials: 'include',
      headers: buildHeaders(authToken),
      cache: 'no-store',
    });
    setRecentReviewsData(Array.isArray(data) ? data : []);
  } catch (error) {
    console.error('Failed to refresh recent reviews', error);
  }
}

async function refreshDashboardData(authToken) {
  await refreshOverview(authToken);
  await refreshWidgetCards(authToken);
  await refreshRecentReviews(authToken);
  await refreshAllCharts(authToken);
}

function scheduleDashboardRefresh(authToken) {
  dashboardRefreshChain = dashboardRefreshChain
    .catch(() => {})
    .then(() => refreshDashboardData(authToken));

  dashboardRefreshChain.catch((error) => {
    console.error('Dashboard refresh failed', error);
  });

  return dashboardRefreshChain;
}

function connectDashboardSocket(authToken) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`);

  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.type === 'reviews_updated') {
        scheduleDashboardRefresh(authToken).finally(() => {
          hideJobStatus();
        });
      }
      if (message.type === 'import_progress') {
        const { job_id: jobId, processed = 0, total = null } = message;
        if (jobId) {
          pendingJobs.set(jobId, { processed, total });
        }
        const totalSafe = total ?? '?';
        setJobMessage(`Обработка отзывов… ${processed}/${totalSafe}`);
        showJobStatus();
      }
      if (message.type === 'import_completed') {
        if (!message.job_id || pendingJobs.has(message.job_id)) {
          if (message.job_id) pendingJobs.delete(message.job_id);
          hideJobStatus();
          const count = message.count ?? 0;
          showToast(`Imported ${count} reviews.`, 'success');
        }
      }
    } catch (error) {
      console.error('Failed to handle dashboard message', error);
    }
  };

  socket.onclose = () => {
    setTimeout(() => connectDashboardSocket(authToken), 3000);
  };

  socket.onerror = () => {
    socket.close();
  };
}

function initDashboard() {
  hideJobStatus(true);
  initFlashMessages();
  const authNode = document.getElementById('auth-data');
  const authToken = authNode ? authNode.dataset.token || '' : '';

  attachJobStatusToForms('.upload-form', 'Загрузка отзывов…');

  captureRecentReviewsDom();
  hydrateRecentReviewsFromPayload();

  scheduleDashboardRefresh(authToken);
  connectDashboardSocket(authToken);

  setInterval(() => {
    scheduleDashboardRefresh(authToken);
  }, 5000);
}

document.addEventListener('DOMContentLoaded', initDashboard);
