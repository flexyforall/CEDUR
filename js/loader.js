/* CEDUR loader sequence.
 *
 * Card positions for the dance are sampled from the reference video
 * (7-second loop, three arrangements):
 *   layout A (0.0s) -> layout B (2.5s) -> layout C (5.0s) -> layout A ...
 * After one full cycle the cards assemble into the Figma collage
 * (frame 227:787), the center card grows in two steps (227:819, 227:835),
 * its video starts, and the card expands to full screen revealing the hero.
 *
 * Click anywhere on the loader to skip.
 */

(function () {
  var loader = document.getElementById('loader');
  var stage = document.getElementById('stage');
  var mark = document.getElementById('loadingMark');
  var loaderVideo = document.getElementById('loaderVideo');
  var cards = {};
  document.querySelectorAll('.tile').forEach(function (el) {
    cards[el.dataset.card] = el;
  });

  /* [left, top, width, height] on the 1440×800 canvas */
  var LAYOUTS = {
    A: {
      c53:  [140, 208, 160, 160],
      c56:  [722,   6, 302, 302],
      c58:  [1045, 300, 214, 214],
      c52:  [504, 387, 243, 243],
      c54:  [187, 585, 144, 144],
      hero: [1062, 549, 242, 242]
    },
    B: {
      c53:  [232,   9, 243, 243],
      c56:  [1092,  97, 121, 121],
      c58:  [1078, 597, 157, 157],
      c52:  [105, 334, 169, 169],
      c54:  [313, 549, 216, 216],
      hero: [645, 253, 312, 312]
    },
    C: {
      c53:  [878,  45, 243, 243],
      c56:  [1000, 320, 304, 304],
      c58:  [654, 595, 151, 151],
      c52:  [117, 522, 289, 289],
      c54:  [574, 297, 216, 216],
      hero: [166, 107, 190, 190]
    },
    /* Figma collage, frame 227:787 */
    FINAL: {
      c53:  [90,  135, 216, 216],
      c56:  [840,   0, 278, 278],
      c58:  [1158, 371, 190, 190],
      c52:  [235, 627, 184, 184],
      c54:  [347, 417, 144, 144],
      hero: [533, 222, 375, 356]
    },
    /* frame 227:819 -> 227:835 -> full screen */
    GROW1: { hero: [385.5, 222, 637, 356] },
    GROW2: { hero: [220, 121, 1000, 558.87] },
    FULL:  { hero: [0, 0, 1440, 800] }
  };

  function apply(layout) {
    Object.keys(layout).forEach(function (key) {
      var el = cards[key];
      var r = layout[key];
      el.style.left = r[0] + 'px';
      el.style.top = r[1] + 'px';
      el.style.width = r[2] + 'px';
      el.style.height = r[3] + 'px';
    });
  }

  function fit() {
    var scale = Math.max(window.innerWidth / 1440, window.innerHeight / 800);
    stage.style.transform = 'translate(-50%, -50%) scale(' + scale + ')';
  }
  window.addEventListener('resize', fit);
  fit();

  var timers = [];
  var finished = false;

  function at(ms, fn) {
    timers.push(setTimeout(fn, ms));
  }

  function finish() {
    if (finished) return;
    finished = true;
    timers.forEach(clearTimeout);

    var heroVideo = document.getElementById('heroVideo');
    try { heroVideo.currentTime = loaderVideo.currentTime || 0; } catch (e) {}
    heroVideo.play().catch(function () {});

    loader.classList.add('is-done');
    document.body.classList.remove('is-locked');
    if (window.CEDUR && window.CEDUR.onLoaderDone) window.CEDUR.onLoaderDone();

    setTimeout(function () { loader.remove(); }, 900);
  }

  function play() {
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      apply(LAYOUTS.FINAL);
      apply(LAYOUTS.FULL);
      Object.keys(cards).forEach(function (k) { cards[k].classList.add('is-in'); });
      finish();
      return;
    }

    apply(LAYOUTS.A);

    /* LOADING mark on black */
    at(200, function () { mark.classList.add('is-in'); });

    /* cards of layout A appear with a quick stagger */
    var order = ['c56', 'c53', 'c58', 'c52', 'c54', 'hero'];
    order.forEach(function (key, i) {
      at(500 + i * 120, function () { cards[key].classList.add('is-in'); });
    });

    /* the dance: A (hold) -> B (hold) -> C (hold) -> A, like the video loop */
    at(1900, function () { apply(LAYOUTS.B); });
    at(4000, function () { apply(LAYOUTS.C); });
    at(6100, function () { apply(LAYOUTS.A); });

    /* assemble into the Figma collage */
    at(7600, function () {
      stage.classList.add('is-settling');
      apply(LAYOUTS.FINAL);
    });

    /* center grows, side cards dim */
    at(9200, function () {
      stage.classList.add('is-dimmed');
      apply(LAYOUTS.GROW1);
    });

    /* final growth step — the video comes alive */
    at(10500, function () {
      apply(LAYOUTS.GROW2);
      loaderVideo.play().catch(function () {});
    });

    /* expand to full screen and hand off to the hero */
    at(12300, function () {
      apply(LAYOUTS.FULL);
      mark.classList.add('is-out');
    });

    at(13300, finish);
  }

  loader.addEventListener('click', finish);
  play();
})();
