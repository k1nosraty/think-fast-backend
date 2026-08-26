import crypto from "k6/crypto";
import http from "k6/http";
import ws from "k6/ws";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const fixtures = new SharedArray("fixtures", () => JSON.parse(open(__ENV.LOAD_FIXTURE_FILE)));
const profile = __ENV.PROFILE || "guess_sustained";
const baseUrl = __ENV.BASE_URL;
const wsUrl = baseUrl.replace(/^http/, "ws");

const scenarios = {
  guess_sustained: {
    executor: "constant-arrival-rate", exec: "guess", rate: 100, timeUnit: "1s",
    duration: "5m", preAllocatedVUs: 200, maxVUs: 500,
  },
  guess_burst: {
    executor: "constant-arrival-rate", exec: "guess", rate: 300, timeUnit: "1s",
    duration: "30s", preAllocatedVUs: 400, maxVUs: 800,
  },
  sockets_2000: {executor: "constant-vus", exec: "socketHold", vus: 2000, duration: "5m"},
  reconnect_1000: {
    executor: "constant-arrival-rate", exec: "reconnect", rate: 17, timeUnit: "1s",
    duration: "60s", preAllocatedVUs: 100, maxVUs: 300,
  },
};

export const options = {
  scenarios: {[profile]: scenarios[profile]},
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<300"],
    checks: ["rate>0.99"],
  },
};

function fixture() { return fixtures[(__VU + __ITER) % fixtures.length]; }
function headers(row) {
  return {"Authorization": `Bearer ${row.token}`, "Content-Type": "application/json"};
}

export function guess() {
  const row = fixture();
  const response = http.post(
    `${baseUrl}/api/v1/matches/${row.match_id}/guesses/`,
    JSON.stringify({command_id: crypto.randomUUID(), guess: row.guess}),
    {headers: headers(row)},
  );
  check(response, {"guess accepted": (item) => item.status === 201});
}

export function socketHold() {
  const row = fixture();
  const response = ws.connect(
    `${wsUrl}/ws/v1/matches/${row.match_id}/`,
    {headers: {Authorization: `Bearer ${row.token}`, Origin: baseUrl}},
    (socket) => { socket.setTimeout(() => socket.close(), 295000); },
  );
  check(response, {"socket upgraded": (item) => item && item.status === 101});
}

export function reconnect() {
  const row = fixture();
  const response = ws.connect(
    `${wsUrl}/ws/v1/matches/${row.match_id}/`,
    {headers: {Authorization: `Bearer ${row.token}`, Origin: baseUrl}},
    (socket) => { socket.setTimeout(() => socket.close(), 250); },
  );
  check(response, {"reconnect upgraded": (item) => item && item.status === 101});
  sleep(0.01);
}
