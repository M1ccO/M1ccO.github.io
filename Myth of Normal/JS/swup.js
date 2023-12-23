// Functions.js

const swup = new Swup();

import Swup from 'swup';
import SwupScrollPlugin from 'swup/plugins/scrollPlugin';

const swup = new Swup({
  plugins: [new SwupScrollPlugin({
    doScrollingRightAway: false,
    animateScroll: true,
    scrollFriction: 0.3,
    scrollAcceleration: 0.04
  })],
  linkSelector: 'a[href^="/"]:not([data-no-swup]), a[href^="#"]'
});


