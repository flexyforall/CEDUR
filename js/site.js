/* CEDUR site behaviour: hero reveal after the loader, compact menu on scroll,
 * masked title reveals, and the pinned point card that switches content
 * (01 -> 04) while the side photo columns scroll up past it. */

(function () {
  var POINTS = [
    {
      num: '01',
      title: 'Made to Weather the Storm',
      text: 'Exceptional impact resistance provides dependable protection against hail and severe weather, season after season.'
    },
    {
      num: '02',
      title: 'Standalone Class A Fire Rated',
      text: 'The highest fire rating available, achieved without special underlayment. CEDUR shakes protect what matters most, by design.'
    },
    {
      num: '03',
      title: 'Strength, Thoughtfully Engineered',
      text: 'Every shake is engineered for lasting structural integrity — lightweight, walkable, and built to hold its beauty for decades.'
    },
    {
      num: '04',
      title: '50-Year Limited Warranty',
      text: 'A commitment built into every shake. CEDUR roofs are made to last a lifetime, and they’re backed by our enduring commitment to quality.'
    }
  ];

  var menu = document.getElementById('menu');
  var hero = document.getElementById('hero');
  var chooseTitle = document.getElementById('chooseTitle');
  var stageEl = document.getElementById('pointsStage');
  var swap = document.getElementById('pointSwap');
  var numEl = document.getElementById('pointNum');
  var titleEl = document.getElementById('pointTitle');
  var textEl = document.getElementById('pointText');
  var rowsEl = document.getElementById('pointRows');

  var active = 0;
  var switching = false;

  var PLUS_SVG = '<svg viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="#020202" stroke-width="1.8" stroke-linecap="round"/></svg>';

  function renderRows() {
    rowsEl.innerHTML = '';
    POINTS.forEach(function (p, i) {
      if (i === active) return;
      var row = document.createElement('button');
      row.className = 'point-row';
      row.type = 'button';
      row.innerHTML = '<span>' + (i + 1) + '. ' + p.title + '</span>' + PLUS_SVG;
      row.addEventListener('click', function () { scrollToPoint(i); });
      rowsEl.appendChild(row);
    });
  }

  function setPoint(i) {
    if (i === active || switching) return;
    switching = true;
    var target = POINTS[i];
    swap.classList.add('is-leaving');
    setTimeout(function () {
      numEl.textContent = target.num;
      titleEl.textContent = target.title;
      textEl.textContent = target.text;
      active = i;
      renderRows();
      swap.classList.remove('is-leaving');
      swap.classList.add('is-entering');
      setTimeout(function () {
        swap.classList.remove('is-entering');
        switching = false;
        update(); /* catch up if scroll moved past another threshold meanwhile */
      }, 500);
    }, 350);
  }

  function stageProgress() {
    var rect = stageEl.getBoundingClientRect();
    var vh = window.innerHeight;
    /* progress of the pinned card through the stage: 0 when the card first
       centers, 1 when the columns run out */
    var total = rect.height - vh;
    if (total <= 0) return 0;
    return Math.min(1, Math.max(0, -rect.top / total));
  }

  function pointIndexFromScroll() {
    var p = stageProgress();
    return Math.min(POINTS.length - 1, Math.floor(p * POINTS.length));
  }

  function scrollToPoint(i) {
    var rect = stageEl.getBoundingClientRect();
    var total = rect.height - window.innerHeight;
    var top = window.scrollY + rect.top;
    var targetP = (i + 0.5) / POINTS.length;
    window.scrollTo({ top: top + targetP * total, behavior: 'smooth' });
  }

  function update() {
    /* compact menu once the hero is left */
    if (window.scrollY > hero.offsetHeight - 120) {
      menu.classList.add('is-compact');
    } else {
      menu.classList.remove('is-compact');
    }
    setPoint(pointIndexFromScroll());
  }

  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);

  /* masked reveal for the section title when it enters the viewport */
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) {
        e.target.classList.add('is-revealed');
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.4 });
  io.observe(chooseTitle);

  renderRows();

  window.CEDUR = window.CEDUR || {};
  window.CEDUR.onLoaderDone = function () {
    document.body.classList.add('is-ready');
    hero.classList.add('is-revealed');
    update();
  };

  /* no loader present (e.g. reduced motion removed it early) */
  if (!document.getElementById('loader')) {
    window.CEDUR.onLoaderDone();
  }
})();
