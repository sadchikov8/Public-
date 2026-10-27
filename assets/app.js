(function () {
  // фото, що не завантажилось → заглушка
  document.querySelectorAll('.card-ph img').forEach(function (im) {
    im.addEventListener('error', function () {
      var d = document.createElement('div'); d.className = 'ph-empty';
      d.innerHTML = '<span></span>Фото скоро';
      d.firstChild.textContent = (im.closest('.card').dataset.brand || '');
      im.replaceWith(d);
    });
    if (im.complete && !im.naturalWidth) im.dispatchEvent(new Event('error'));
  });

  // ---------- каталог: фільтри ----------
  var grid = document.getElementById('grid');
  if (grid) {
    var cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
    var original = cards.slice();
    var state = { cond: '', where: '', type: '', brand: '', price: '', sort: '' };
    try {
      var saved = new URLSearchParams(location.search);
      Object.keys(state).forEach(function (k) { if (saved.get(k)) state[k] = saved.get(k); });
    } catch (e) {}

    function apply() {
      var shown = 0, lo = 0, hi = Infinity;
      if (state.price) { var r = state.price.split('-'); lo = +r[0]; hi = +r[1]; }
      cards.forEach(function (c) {
        var d = c.dataset, p = +d.price;
        var ok = (!state.cond || d.cond === state.cond) &&
                 (!state.where || d.where === state.where) &&
                 (!state.type || d.type === state.type) &&
                 (!state.brand || d.brand === state.brand) &&
                 (!state.price || (p >= lo && p <= hi));
        c.classList.toggle('hide', !ok);
        if (ok) shown++;
      });
      var list = original.slice();
      if (state.sort) {
        var s = state.sort.split('-'), key = s[0], dir = s[1] === 'desc' ? -1 : 1;
        list.sort(function (a, b) {
          var x = +a.dataset[key] || 9e9, y = +b.dataset[key] || 9e9;
          if (dir < 0) { x = +a.dataset[key] || 0; y = +b.dataset[key] || 0; }
          return (x - y) * dir;
        });
      }
      list.forEach(function (c) { grid.appendChild(c); });
      document.getElementById('found').textContent = 'Знайдено: ' + shown;
      document.getElementById('empty').style.display = shown ? 'none' : 'block';
      try {
        var q = new URLSearchParams();
        Object.keys(state).forEach(function (k) { if (state[k]) q.set(k, state[k]); });
        history.replaceState(null, '', q.toString() ? '?' + q : location.pathname);
      } catch (e) {}
    }

    document.querySelectorAll('.seg').forEach(function (seg) {
      var f = seg.dataset.f;
      seg.querySelectorAll('button').forEach(function (b) {
        b.classList.toggle('on', b.dataset.v === state[f]);
        b.addEventListener('click', function () {
          state[f] = b.dataset.v;
          seg.querySelectorAll('button').forEach(function (x) { x.classList.toggle('on', x === b); });
          apply();
        });
      });
    });
    document.querySelectorAll('select[data-f]').forEach(function (s) {
      s.value = state[s.dataset.f];
      s.addEventListener('change', function () { state[s.dataset.f] = s.value; apply(); });
    });
    apply();
  }

  // ---------- сторінка авто: галерея ----------
  var gal = document.getElementById('gal');
  if (gal) {
    var track = gal.querySelector('.gal-track');
    var imgs = Array.prototype.slice.call(track.querySelectorAll('img'));
    var n = gal.querySelector('.gal-n b');
    var idx = 0;
    track.addEventListener('scroll', function () {
      idx = Math.round(track.scrollLeft / track.clientWidth);
      if (n) n.textContent = idx + 1;
    }, { passive: true });

    // лайтбокс
    var lb = document.createElement('div');
    lb.className = 'lb';
    lb.innerHTML = '<img alt=""><button class="x" aria-label="Закрити">×</button>' +
                   '<button class="l" aria-label="Назад">‹</button><button class="r" aria-label="Далі">›</button>';
    document.body.appendChild(lb);
    var big = lb.querySelector('img');
    function show(i) { idx = (i + imgs.length) % imgs.length; big.src = imgs[idx].src; }
    imgs.forEach(function (im, i) { im.addEventListener('click', function () { show(i); lb.classList.add('on'); }); });
    lb.querySelector('.x').onclick = function () { lb.classList.remove('on'); };
    lb.querySelector('.l').onclick = function () { show(idx - 1); };
    lb.querySelector('.r').onclick = function () { show(idx + 1); };
    var tx = 0;
    lb.addEventListener('touchstart', function (e) { tx = e.touches[0].clientX; }, { passive: true });
    lb.addEventListener('touchend', function (e) {
      var dx = e.changedTouches[0].clientX - tx;
      if (Math.abs(dx) > 40) show(idx + (dx < 0 ? 1 : -1));
    });
    document.addEventListener('keydown', function (e) {
      if (!lb.classList.contains('on')) return;
      if (e.key === 'Escape') lb.classList.remove('on');
      if (e.key === 'ArrowLeft') show(idx - 1);
      if (e.key === 'ArrowRight') show(idx + 1);
    });
  }
})();
