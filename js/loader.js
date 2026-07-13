/* CEDUR loader sequence — plays the four Figma frames as one timeline:
 *   1. black screen, LOADING kinetic wordmark fades in    (frame 218:593)
 *   2. collage tiles pop in one by one, center image last (frame 227:787)
 *   3. side tiles dim, center image grows to 637×356      (frame 227:819)
 *   4. center grows to 1000×559 and its video starts      (frame 227:835)
 * Click anywhere to replay.
 */

(function () {
  var stage = document.getElementById('stage');
  var hero = document.getElementById('hero');
  var heroVideo = document.getElementById('heroVideo');
  var mark = document.getElementById('loadingMark');
  var tiles = Array.prototype.slice.call(document.querySelectorAll('[data-tile]'));
  var timers = [];

  // Scale the 1440×800 canvas to cover the viewport
  function fit() {
    var scale = Math.max(window.innerWidth / 1440, window.innerHeight / 800);
    stage.style.transform = 'translate(-50%, -50%) scale(' + scale + ')';
  }
  window.addEventListener('resize', fit);
  fit();

  function at(ms, fn) {
    timers.push(setTimeout(fn, ms));
  }

  function play() {
    timers.forEach(clearTimeout);
    timers = [];

    stage.classList.remove('is-dimmed');
    hero.classList.remove('is-in', 'is-grow-1', 'is-grow-2');
    mark.classList.remove('is-in');
    tiles.forEach(function (t) { t.classList.remove('is-in'); });
    heroVideo.pause();
    try { heroVideo.currentTime = 0; } catch (e) {}

    // force reflow so the reset state is committed before replaying
    void stage.offsetWidth;

    // Frame 1: LOADING appears on black
    at(200, function () { mark.classList.add('is-in'); });

    // Frame 2: tiles pop in staggered, center image last
    tiles.forEach(function (tile, i) {
      at(800 + i * 280, function () { tile.classList.add('is-in'); });
    });
    at(800 + tiles.length * 280 + 100, function () { hero.classList.add('is-in'); });

    // Frame 3: center grows, everything else dims
    at(3600, function () {
      hero.classList.add('is-grow-1');
      stage.classList.add('is-dimmed');
    });

    // Frame 4: center grows to its final size and the video comes alive
    at(4900, function () {
      hero.classList.add('is-grow-2');
      heroVideo.play().catch(function () {});
    });
  }

  document.getElementById('loader').addEventListener('click', play);
  play();
})();
