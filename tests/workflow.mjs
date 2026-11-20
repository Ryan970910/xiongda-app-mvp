import assert from 'node:assert/strict';
import { initialState, newTask, projectsFor, transition } from '../model.js';

const state = initialState();
const order = state.orders[1];
const research = state.tasks.find(t => t.orderId === order.id);
const finance = newTask(order, 'finance', order.deadline);
state.tasks.push(finance);
assert.notEqual(finance.id, newTask(order, 'finance', order.deadline).id);

// A major project becomes available on director approval, before client sign-off.
transition(state, research, 'reviewer', 'approve');
assert.equal(projectsFor(state, order.id).length, 0);
transition(state, research, 'director', 'approve');
assert.equal(research.status, 'customer');
assert.equal(projectsFor(state, order.id).length, 1);
transition(state, finance, 'finance', 'accept');
finance.draft.summary = '本期无费用';
finance.draft.evidence = '本月凭证核对记录';
transition(state, finance, 'finance', 'submit');
assert.equal(finance.versions[0].fees.length, 0);
assert.equal(finance.versions[0].projects[0].budget, 22000000);

// A client return does not expose unapproved edits or rewrite an earlier filing.
transition(state, research, 'dispatcher', 'revise', '调整下期预算');
research.draft.projects[0].budget = 23000000;
assert.equal(projectsFor(state, order.id)[0].budget, 22000000);
transition(state, research, 'research', 'submit');
for (const role of ['lead','reviewer','director']) transition(state, research, role, 'approve');
assert.equal(projectsFor(state, order.id)[0].budget, 23000000);
assert.equal(finance.versions[0].projects[0].budget, 22000000);

// A second approved research task extends the same order's project list.
const second = newTask(order, 'research', order.deadline);
state.tasks.push(second);
transition(state, second, 'research', 'accept');
second.draft = structuredClone(research.draft);
second.draft.projects[0].id = 'RD-005';
transition(state, second, 'research', 'submit');
transition(state, second, 'lead', 'approve');
transition(state, second, 'reviewer', 'approve');
assert.equal(projectsFor(state, order.id).length, 2);
assert.equal(finance.versions[0].projects.length, 1);
console.log('PASS split tasks, internal handoff, empty fees and immutable finance snapshots');
