const chartRegistry = {};
const pendingJobs = new Map();

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

function setOverlayMessage(message) {
  const overlay = document.getElementById('loading-overlay');
  if (!overlay) return;
  const text = overlay.querySelector('p');
  if (text) {
    text.textContent = message || 'Processing…';
  }
}

function showOverlay(message) {
  const overlay = document.getElementById('loading-overlay');
  if (!overlay) return;
  setOverlayMessage(message);
  overlay.classList.remove('hidden');
}

function hideOverlay() {
  const overlay = document.getElementById('loading-overlay');
  if (!overlay) return;
  overlay.classList.add('hidden');
}

function initFlashMessages() {
  const flashNode = document.getElementById('flash-data');
  if (!flashNode) return;
  const { status, error, job } = flashNode.dataset;
  if (error) {
    showToast(error, 'error');
  } else if (status) {
    showToast(status, 'success');
  }

  if (job) {
    pendingJobs.set(job, { processed: 0, total: null });
    showOverlay('Import started…');
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

function attachOverlayToForms(selector, message) {
  document.querySelectorAll(selector).forEach((form) => {
    form.addEventListener('submit', () => {
      showOverlay(message);
    });
  });
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

function loadWidgetChart(card, authToken) {
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

  const headers = authToken
    ? {
        Authorization: `Bearer ${authToken}`,
      }
    : {};

  fetch(`/dashboard/widgets/${widgetId}/timeseries`, {
    credentials: 'include',
    headers,
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error('Failed to load widget data');
      }
      return response.json();
    })
    .then((payload) => {
      const data = payload.data || [];
      const labels = data.map((item) => item.date);
      const values = data.map((item) => item.value);
      renderChart(card, labels, values, visualization, metric);
    })
    .catch((error) => {
      console.error(error);
      canvas.replaceWith('Unable to load chart');
    });
}

function refreshAllCharts(authToken) {
  document.querySelectorAll('.widget-card').forEach((card) => {
    const visualization = card.dataset.visualization;
    if (!visualization || visualization === 'metric') return;
    loadWidgetChart(card, authToken);
  });
}

function refreshOverview(authToken) {
  const headers = authToken
    ? {
        Authorization: `Bearer ${authToken}`,
      }
    : {};

  fetch('/analytics/overview', {
    credentials: 'include',
    headers,
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error('Failed to load overview');
      }
      return response.json();
    })
    .then((data) => {
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
    })
    .catch((error) => {
      console.error(error);
    });
}

function refreshRecentReviews(authToken) {
  const headers = authToken
    ? {
        Authorization: `Bearer ${authToken}`,
      }
    : {};

  fetch('/reviews/recent', {
    credentials: 'include',
    headers,
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error('Failed to load recent reviews');
      }
      return response.json();
    })
    .then((data) => {
      const tbody = document.getElementById('recent-reviews-body');
      if (!tbody) return;
      tbody.innerHTML = '';
      data.forEach((review) => {
        const row = document.createElement('tr');
        const date = review.date ? new Date(review.date).toLocaleString() : 'n/a';
        row.innerHTML = `
          <td>${review.id}</td>
          <td>${review.product || '—'}</td>
          <td>${review.sentiment || 'pending'}</td>
          <td>${date}</td>
          <td>${(review.text || '').slice(0, 120)}${(review.text || '').length > 120 ? '…' : ''}</td>
        `;
        tbody.appendChild(row);
      });
    })
    .catch((error) => {
      console.error(error);
    });
}

function connectDashboardSocket(authToken) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`);

  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.type === 'reviews_updated') {
        refreshOverview(authToken);
        refreshAllCharts(authToken);
        refreshRecentReviews(authToken);
        if (pendingJobs.size === 0) {
          hideOverlay();
        }
      }
      if (message.type === 'import_progress') {
        const { job_id: jobId, processed = 0, total = null } = message;
        if (jobId) {
          pendingJobs.set(jobId, { processed, total });
        }
        const totalSafe = total ?? '?';
        setOverlayMessage(`Processing reviews… ${processed}/${totalSafe}`);
        showOverlay();
      }
      if (message.type === 'import_completed') {
        if (!message.job_id || pendingJobs.has(message.job_id)) {
          if (message.job_id) pendingJobs.delete(message.job_id);
          if (pendingJobs.size === 0) {
            hideOverlay();
          }
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
  hideOverlay();
  initFlashMessages();
  const authNode = document.getElementById('auth-data');
  const authToken = authNode ? authNode.dataset.token || '' : '';

  attachOverlayToForms('.upload-form', 'Importing reviews…');
  attachOverlayToForms('.widget-form', 'Saving widget…');
  attachOverlayToForms('form[action*="/widgets/"]', 'Updating dashboard…');

  refreshOverview(authToken);
  refreshAllCharts(authToken);
  refreshRecentReviews(authToken);
  connectDashboardSocket(authToken);

  setInterval(() => {
    refreshRecentReviews(authToken);
    refreshOverview(authToken);
  }, 15000);
}

document.addEventListener('DOMContentLoaded', initDashboard);
