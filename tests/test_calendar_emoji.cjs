const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('deployment/markAcceptedMeetings_noNotify.gs', 'utf8');
let cases = 0;
const me = 'barbara.pigg@whiteboardgeeks.com';
function run(event, calendar = {id: me, primary: true, accessRole: 'owner'}) {
  cases++;
  const writes = [];
  vm.runInNewContext(source + '\nmarkAcceptedMeetingsAcrossCalendarsWithPagination();', {
    Session: {getEffectiveUser: () => ({getEmail: () => me})}, Logger: {log() {}},
    Calendar: {CalendarList: {list: () => ({items: [calendar]})},
      Events: {list: () => ({items: [event]}), patch: (...args) => writes.push(args)}},
  });
  assert.ok(writes.every(w => w[3].sendUpdates === 'none'));
  assert.ok(writes.every(w => Object.keys(w[0]).join() === 'summary'));
  return writes.map(w => w[0].summary);
}
const copy = {id: 'original-id', iCalUID: 'original-uid', privateCopy: true,
  organizer: {email: 'barbara@wbgcontact.com'}, summary: 'Intro Lead',
  description: 'Check the <b>quarantine folder</b>',
  attendees: [{email: me, self: true, responseStatus: 'accepted'},
              {email: 'lead@example.test', responseStatus: 'accepted'}]};
assert.deepEqual(run(copy), ['📦 Intro Lead']);
assert.deepEqual(run({...copy, description: 'Video Brochure'}), ['📬 Intro Lead']);
assert.deepEqual(run({...copy, summary: 'Follow-up'}), ['✅ Follow-up']);
assert.deepEqual(run({...copy, summary: '📬 📦 ✅ Intro Lead'}), ['📦 Intro Lead']);
assert.deepEqual(run({...copy, summary: '📦 Intro Lead'}), []);
for (const responseStatus of ['needsAction', 'tentative', 'declined']) {
  const attendees = [copy.attendees[0], {...copy.attendees[1], responseStatus}];
  assert.deepEqual(run({...copy, summary: '📦 Intro Lead', attendees}), ['Intro Lead']);
  assert.deepEqual(run({...copy, attendees}), []);
}
assert.deepEqual(run({...copy, attendees: [{email: me.toUpperCase(), responseStatus: 'accepted'}]}), []);
assert.deepEqual(run({...copy, attendees: [{email: 'alias@example.test', self: true, responseStatus: 'accepted'}]}), []);
assert.deepEqual(run({...copy, attendees: [{email: 'BARBARA@WBGCONTACT.COM', responseStatus: 'accepted'}]}), []);
assert.deepEqual(run({...copy, privateCopy: false}), []);
assert.deepEqual(run(copy, {id: 'other', primary: false, accessRole: 'owner'}), []);
assert.deepEqual(run(copy, {id: me, primary: true, accessRole: 'reader'}), []);
assert.deepEqual(run({...copy, privateCopy: false, organizer: {email: me.toUpperCase()}}), ['📦 Intro Lead']);
assert.deepEqual(run({...copy, summary: ''}), []);
assert.deepEqual(run({...copy, attendees: []}), []);
console.log(`Calendar emoji: ${cases} cases passed; summary-only, no-notification writes.`);
