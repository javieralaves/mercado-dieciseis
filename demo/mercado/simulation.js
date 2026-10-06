/* Read-only replay. All computations and decisions originate in reproduce.py. */
let data, selected = 0, step = 0;
const $ = id => document.getElementById(id);
const p = value => `${value} P`;
const signed = value => `${value > 0 ? '+' : ''}${value} P`;
function cells(body, rows) {
  body.replaceChildren();
  rows.forEach(row => {
    const tr = document.createElement('tr');
    row.forEach(value => {const td = document.createElement('td');td.textContent = value;tr.append(td);});
    body.append(tr);
  });
}
function lines(id, values) {
  $(id).replaceChildren();
  values.forEach(value => {const el = document.createElement('p');el.textContent = value;$(id).append(el);});
}
function render() {
  const s = data.scenarios[selected], f = s.frames[step], team = $('team').value;
  $('position').textContent = `Step ${step + 1} of ${s.frames.length}`;
  $('previous').disabled = step === 0;
  $('next').disabled = $('finish').disabled = step === s.frames.length - 1;
  $('phase').textContent = `Tick ${f.tick} · ${f.state.replaceAll('_', ' ')}`;
  $('stage-title').textContent = f.label;
  const descriptions = [
    'These structured swap negotiations ended without a trade. No new counterparties are introduced in the historical baseline.',
    'Local agents inspect failed threads, spare ownership, current values and available cash. Only safe, consented intentions are submitted.',
    'The exact private proposal must pass local limits and receive every participant’s buy-in before execution instructions appear.',
    'Sellers create directed offers; buyers revalidate before acceptance. A changed value creates a persistent human-required stop.',
    'Acceptance queues a bilateral trade. A stopped route cannot reverse an acceptance already made.',
    'The simulated server settles queued offers. Agents read actual settlements and reconcile inventory, price and fee.'
  ];
  $('stage-copy').textContent = descriptions[step];
  $('timeline').replaceChildren(...s.frames.map((_,i)=>{const el=document.createElement('span');el.className=i<=step?'active':'';return el;}));
  $('trades').textContent = f.trades;
  $('gain').textContent = signed(f.participant_gain);
  $('fees').textContent = p(f.fees);
  $('gross').textContent = p(f.participant_gain + f.fees);
  const h = s.history.find(x=>x.team===team);
  lines('history', [`${team} offered its spare ${h.offered} for ${h.wanted}.`, `Counterparty: ${h.counterparty}. Outcome: ${h.outcome}.`, h.reason]);
  const view = step ? s.views[team] : null;
  const row = f.teams.find(x=>x.team===team);
  if (view) {
    const cost=view.cash_paid+view.buyer_fee, initial=s.frames[0].teams.find(x=>x.team===team);
    lines('proposal', [`Sell ${view.give.card}: receive ${p(view.cash_received)}.`, `Buy ${view.receive.card}: pay ${p(view.cash_paid)} + ${p(view.buyer_fee)} fee.`, `Estimated benefit at proposal: ${signed(view.cash_received-initial.outgoing_value+initial.incoming_value-cost)}.`, `Cash after buying before selling: ${p(initial.cash-cost)}.`, 'This view omits other teams’ private values and the full route. Approval does not authorize changed terms.']);
  } else lines('proposal',[step ? 'No compatible route was offered. Safe cash bounds may prevent sharing a usable intention.' : 'No proposal yet. Start the replay to observe the agents.']);
  const evaluator=$('evaluator').checked;
  cells($('holdings'),f.teams.filter(x=>evaluator||x.team===team).map(x=>[x.team,p(x.cash),x.holdings.join(', '),p(x.outgoing_value),p(x.incoming_value),signed(x.gain),x.human_required?'Required':'Clear']));
  cells($('offers'),f.offers.filter(o=>evaluator||o.seller===team||o.buyer===team).map(o=>[o.seller,o.buyer,o.card,p(o.price),p(o.fee),o.status]));
  if (!$('offers').children.length) cells($('offers'),[['No visible offers at this step.','','','','','']]);
  $('notice').hidden = !f.notices.length;
  // System-wide stop notices are explicitly evaluator evidence, not participant disclosures.
  lines('notice',f.notices.filter(n=>evaluator||n.startsWith(team+':')||!n.includes('AskQuestions')));
  if (!evaluator && row.human_required) lines('notice',[`${team}: persistent HUMAN_REQUIRED gate. No automatic restart can clear this decision.`]);
}
function selectScenario() {
  selected=Number($('scenario').value);step=0;
  $('team').replaceChildren(...data.scenarios[selected].frames[0].teams.map(t=>{const o=document.createElement('option');o.value=t.team;o.textContent=t.team;return o;}));
  render();
}
$('scenario').addEventListener('change',selectScenario);
$('team').addEventListener('change',render);
$('evaluator').addEventListener('change',render);
$('previous').addEventListener('click',()=>{step=Math.max(0,step-1);render();});
$('next').addEventListener('click',()=>{step=Math.min(data.scenarios[selected].frames.length-1,step+1);render();});
$('finish').addEventListener('click',()=>{step=data.scenarios[selected].frames.length-1;render();});
$('reset').addEventListener('click',()=>{step=0;render();});
fetch('/simulation-results.json').then(r=>{if(!r.ok)throw Error('evidence unavailable');return r.json();}).then(result=>{
  data=result;
  $('scenario').replaceChildren(...data.scenarios.map((s,i)=>{const o=document.createElement('option');o.value=i;o.textContent=s.title;return o;}));
  $('scenario').disabled=$('team').disabled=false;
  $('loader').hidden=true;$('results').hidden=false;selectScenario();
}).catch(()=>{$('loader').textContent='Could not load the replay evidence. Reload this page to try again. No market action was performed.';});
