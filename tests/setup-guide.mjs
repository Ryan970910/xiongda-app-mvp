import assert from 'node:assert/strict';
import { applicable, makePlan } from '../setup-guide/questions.js';

let combinations = 0;
function walk(answers) {
  const next = applicable(answers).find(q => !answers[q.id]);
  if (next) {
    for (const [value] of next.options) walk({...answers, [next.id]: value});
    return;
  }
  const {now, later, messages, headline} = makePlan(answers);
  const cards = [...now, ...later];
  assert.ok(headline && now.length && messages.length);
  assert.equal(new Set(cards.map(c => c.id)).size, cards.length);
  for (const card of cards) assert.ok(card.who && card.actions.length >= 2 && card.done);
  assert.ok(!JSON.stringify({cards,messages}).includes('undefined'));
  assert.equal(cards.some(c => c.id === 'sandbox'), ['ours','client','both'].includes(answers.seal));
  assert.equal(now.some(c => c.id === 'host'), ['team','live'].includes(answers.stage));
  assert.equal(cards.some(c => c.link?.[0].includes('备案')), answers.region === 'mainland');
  combinations++;
}
walk({});
console.log('PASS',combinations,'valid preparation plans');
