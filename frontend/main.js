const API_URL = (window.location.protocol === 'file:' || window.location.hostname === '127.0.0.1') && !window.location.port.includes('8000') ? 'http://localhost:8000/api' : '/api';

// Tab Switching Logic
window.switchTab = function(tabName) {
  // Update buttons
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  event.target.classList.add('active');

  // Update content sections
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
  document.getElementById(`${tabName}-section`).classList.add('active');
}

// Market Analysis Event
document.getElementById('btn-market-analyze').addEventListener('click', async () => {
  const loader = document.getElementById('market-loader');
  const resultBox = document.getElementById('market-result');
  const btn = document.getElementById('btn-market-analyze');

  btn.disabled = true;
  resultBox.classList.add('hidden');
  loader.classList.remove('hidden');

  try {
    const response = await fetch(`${API_URL}/market-analysis`);
    const data = await response.json();

    if (data.success) {
      resultBox.innerHTML = marked.parse(data.ai_report);
    } else {
      resultBox.innerHTML = `<p style="color:var(--accent-color)">發生錯誤：${data.error}</p>`;
    }
  } catch (error) {
    resultBox.innerHTML = `<p style="color:var(--accent-color)">連線或解析失敗：${error.message}。如果是在雲端，請確定後端沒出錯。</p>`;
  } finally {
    loader.classList.add('hidden');
    resultBox.classList.remove('hidden');
    btn.disabled = false;
  }
});

// Individual Stock Analysis Event
document.getElementById('btn-search').addEventListener('click', async () => {
  const input = document.getElementById('stock-input').value.trim();
  const loader = document.getElementById('stock-loader');
  const resultBox = document.getElementById('stock-result');
  const btn = document.getElementById('btn-search');

  if (!input) {
    alert('請先輸入股號！');
    return;
  }

  btn.disabled = true;
  resultBox.classList.add('hidden');
  loader.classList.remove('hidden');

  try {
    const response = await fetch(`${API_URL}/stock-analysis/${input}`);
    const data = await response.json();

    if (data.success) {
      const headerHtml = `<h2>⭐ ${data.company_name} (${data.symbol})</h2>
                          <p>最新收盤價：${data.recent_close.toFixed(2)}</p><hr style="border-color:rgba(255,255,255,0.1); margin: 15px 0;" />`;
      resultBox.innerHTML = headerHtml + marked.parse(data.ai_report);
    } else {
      resultBox.innerHTML = `<p style="color:var(--accent-color)">發生錯誤：${data.error}</p>`;
    }
  } catch (error) {
    resultBox.innerHTML = `<p style="color:var(--accent-color)">連線或解析失敗：${error.message}。如果是在雲端，請確定後端沒出錯。</p>`;
  } finally {
    loader.classList.add('hidden');
    resultBox.classList.remove('hidden');
    btn.disabled = false;
  }
});

// Allow Enter key for input
document.getElementById('stock-input').addEventListener('keypress', function (e) {
  if (e.key === 'Enter') {
    document.getElementById('btn-search').click();
  }
});

// Recommendations Event
document.getElementById('btn-recommend').addEventListener('click', async () => {
  const loader = document.getElementById('recommend-loader');
  const resultBox = document.getElementById('recommend-result');
  const btn = document.getElementById('btn-recommend');

  btn.disabled = true;
  resultBox.classList.add('hidden');
  loader.classList.remove('hidden');

  try {
    const response = await fetch(`${API_URL}/recommendations`);
    const data = await response.json();

    if (data.success) {
      resultBox.innerHTML = marked.parse(data.ai_report);
    } else {
      resultBox.innerHTML = `<p style="color:var(--accent-color)">發生錯誤：${data.error}</p>`;
    }
  } catch (error) {
    resultBox.innerHTML = `<p style="color:var(--accent-color)">連線或解析失敗：${error.message}。如果是在雲端，請確定後端沒出錯。</p>`;
  } finally {
    loader.classList.add('hidden');
    resultBox.classList.remove('hidden');
    btn.disabled = false;
  }
});
