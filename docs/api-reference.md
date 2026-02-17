# Daktela REST API v6 — Reference

Source: official docs at `customer.daktela.com/apihelp/v6/` (REST API 2025.2 build 321800).

**Base URL**: `https://{instance}.daktela.com/api/v6/{endpoint}.json`
**Auth**: `X-AUTH-TOKEN: {token}` header (recommended)

---

## Filtering, paging, sorting

All list (GET) endpoints accept:

| Parameter | Example | Notes |
|-----------|---------|-------|
| `filter[N][field]` | `filter[0][field]=stage` | Field name to filter on (singular `filter`, not `filters`) |
| `filter[N][operator]` | `filter[0][operator]=eq` | `eq` `neq` `like` `gt` `gte` `lt` `lte` |
| `filter[N][value]` | `filter[0][value]=OPEN` | Filter value |
| `fields[N]` | `fields[0]=name` | Limit returned fields |
| `skip` | `skip=50` | Pagination offset |
| `take` | `take=50` | Page size (max 1000) |
| `sort[N][field]` | `sort[0][field]=created` | Sort field (nested array, not flat) |
| `sort[N][dir]` | `sort[0][dir]=desc` | `asc` or `desc` |

---

## Tickets

`GET /api/v6/tickets.json`
`GET /api/v6/tickets/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | Integer | C+R | Unique ID |
| `title` | String | All | Subject (required) |
| `category` | FK→TicketsCategories | All | Required |
| `user` | FK→Users | All | Assigned agent |
| `contact` | FK→Contacts | All | |
| `email` | Email | C+R | |
| `parentTicket` | FK→Tickets | All | |
| `stage` | Enum | All | Required. `OPEN` `WAIT` `CLOSE` `ARCHIVE` |
| `priority` | Enum | All | Required. `LOW` `MEDIUM` `HIGH` |
| `description` | Text | All | |
| `sla_deadtime` | DateTime | All | Deadline |
| `sla_close_deadline` | DateTime | R | |
| `sla_overdue` | Time sec | R | |
| `sla_duration` | Integer | R | Seconds to SLA deadline |
| `reopen` | DateTime | All | Auto-reopen date |
| `created` | DateTime | R | |
| `edited` | DateTime | R | |
| `last_activity` | DateTime | R | |
| `last_activity_operator` | DateTime | R | |
| `last_activity_client` | DateTime | R | |
| `first_answer` | DateTime | R | |
| `first_answer_deadline` | DateTime | R | |
| `first_answer_duration` | Integer | R | Seconds to first answer |
| `first_answer_overdue` | Time sec | R | First answer overdue time |
| `closed` | DateTime | R | |
| `id_merge` | FK→Tickets | R | Merged-into ticket |
| `isParent` | Boolean | R | Has child tickets |
| `sla_change` | DateTime | R | SLA change time |
| `sla_custom` | Boolean | R | SLA customized |
| `interaction_activity_count` | Integer | R | Total activity count |
| `created_by` | FK→Users | R | Created by |
| `edited_by` | FK→Users | R | Last edited by |
| `unread` | Boolean | R | Has unread messages |
| `last_unread_date` | DateTime | R | Last unread message date |
| `has_attachment` | Boolean | R | Has attachments |
| `followers` | MN→Users | All | |
| `statuses` | MN→Statuses | All | |
| `customFields` | Custom | All | |

---

## TicketsCategories

`GET /api/v6/ticketsCategories.json`
`GET /api/v6/ticketsCategories/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | Unique name |
| `title` | String | All | Display name (required) |
| `description` | String | All | |
| `sla` | FK→TicketsSla | All | Required |
| `timecondition` | FK→Timegroups | All | Working time |
| `email_queue` | FK→Queues | All | |
| `call_queue` | FK→Queues | All | |
| `sms_queue` | FK→Queues | All | |
| `status_required` | Enum | All | `never` `closing_ticket` `always` |
| `allow_external_comments` | Boolean | All | |
| `multiple_statuses` | Boolean | All | |
| `auto_archive_tickets` | Integer | All | Days before auto-archive |

---

## Activities

`GET /api/v6/activities.json`
`GET /api/v6/activities/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | Unique ID |
| `ticket` | FK→Tickets | All | |
| `title` | String | All | Display name |
| `important` | Boolean | All | |
| `action` | Enum | All | `OPEN` `WAIT` `POSTPONE` `CLOSE` |
| `type` | Enum | C+R | `CALL` `EMAIL` `CHAT` `SMS` `FBM` `IGDM` `WAP` `VBR` `CUSTOM` `FBCOMMENT` `IGCOMMENT` `COMMENT` (empty = Comment) |
| `item` | Integer | R | Specific item ID (e.g. Call, Email, Chat record) |
| `queue` | FK→Queues | C+R+U | |
| `user` | FK→Users | C+R | |
| `contact` | FK→Contacts | All | |
| `survey` | FK→NpsSurveys | C+R+U | NPS survey |
| `record` | FK→CampaignsRecords | All | Campaign record |
| `priority` | Integer | C+R | |
| `options` | Json | All | Additional parameters |
| `description` | Html | All | |
| `time` | DateTime | R | Creation time |
| `time_wait` | DateTime | R | Wait time |
| `time_open` | DateTime | R | Open time |
| `time_close` | DateTime | R | Close time |
| `baw` | Time sec | R | Before activity work time |
| `aaw` | Time sec | R | After activity work time |
| `duration` | Time sec | R | |
| `focus_time` | Time sec | R | Active tab focus time |
| `focus_disruptions` | Integer | R | Active tab focus disruptions |
| `ringing_time` | Time sec | R | |
| `created_by` | FK→Users | R | Created by |
| `statuses` | MN→Statuses | All | |
| `anonymized` | Boolean | R | Flag indicating if the activity has been anonymized |
| `customFields` | Custom | All | |

---

## ActivitiesCall

`GET /api/v6/activitiesCall.json`
`GET /api/v6/activitiesCall/{id_call}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `id_call` | String | C+R | Unique call ID (used as {NAME}) |
| `call_time` | DateTime | R | |
| `direction` | Enum | R | `in` `out` `internal` |
| `answered` | Boolean | R | |
| `id_queue` | FK→Queues | R | Queue field name |
| `id_agent` | FK→Users | R | Agent field name |
| `clid` | Phone | R | Caller ID |
| `prefix_clid_name` | String | R | |
| `did` | String | R | Local number |
| `contact` | FK→Contacts | All | |
| `waiting_time` | Time sec | R | |
| `ringing_time` | Time sec | R | |
| `hold_time` | Time sec | R | |
| `duration` | Time sec | R | Answered call duration |
| `disposition_cause` | Enum | R | `caller` `agent` `transfer` `system` |
| `disconnection_cause` | Enum | R | `abandon` `exitwithtimeout` `exitwithkey` `exitempty` `busy` `cancel` `noanswer` `failed` `amdmachine` |
| `pressed_key` | String | R | |
| `missed_call` | Integer | R | 1=missed, 0=called back, null=not missed |
| `missed_call_time` | DateTime | R | When called back |
| `missed_callback` | FK→ActivitiesCall | R | Call with which it was called back |
| `attempts` | Integer | R | Unsuccessful distribution attempts |
| `options` | Json | R | Additional parameters (incl. `missedagentname`) |
| `activities` | →Activities | All | |
| `cdr` | FK→CallDetail | R | Call detail record |

---

## ActivitiesEmail

`GET /api/v6/activitiesEmail.json`
`GET /api/v6/activitiesEmail/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `queue` | FK→Queues | R | Required |
| `user` | FK→Users | R | |
| `contact` | FK→Contacts | All | |
| `title` | String | R | Subject |
| `address` | Email | R | Sender/recipient address |
| `direction` | Enum | R | `in` `out` |
| `wait_time` | Time sec | R | |
| `duration` | Time sec | R | |
| `answered` | Boolean | R | |
| `text` | Html | R | Body |
| `time` | DateTime | R | Email time |
| `state` | Enum | R | `SENT` `FAILED` `WAIT` `POSTPROCESSING` `DRAFT` |
| `options` | Json | R | Additional parameters |
| `activities` | →Activities | R | |

---

## ActivitiesWeb

`GET /api/v6/activitiesWeb.json`
`GET /api/v6/activitiesWeb/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `title` | String | C+R | Customer name |
| `state` | Enum | R | `ROUTING` or empty |
| `user` | FK→Users | R | |
| `queue` | FK→Queues | C+R | |
| `contact` | FK→Contacts | R | |
| `connector` | FK | R | Connector |
| `answered` | Boolean | R | |
| `duration` | Time sec | R | |
| `time` | DateTime | R | |
| `wait_time` | Time sec | R | |
| `routing_duration` | Time sec | C+R | Routing duration |
| `disconnection` | Enum | R+U | `USER` `CLIENT` `TIMEOUT` `NOT_AVAIL` `OUT_OF_TIME` `DECISION_TREE` `BAN` |
| `missed` | Enum | All | `YES` `NO` |
| `missed_time` | DateTime | All | |
| `email` | Email | C+R | |
| `phone` | Phone | C+R | |
| `options` | Json | C+R | Additional parameters |
| `context` | Json | C+R | Context data |
| `host` | String | C+R | Host |
| `referer` | String | C+R | Referrer URL |
| `refererLast` | String | C+R | Last referrer URL |
| `browser` | String | C+R | Browser |
| `mobileDevice` | Boolean | C+R | Mobile device |
| `privateMode` | Boolean | C+R | Private/incognito mode |
| `users` | Json | C+R+U | Users |
| `customer` | Json | C+R | Customer data |
| `customFields` | Json | C+R | Custom fields |
| `hasFocus` | Boolean | C+R | Active tab has focus |
| `isVisible` | Boolean | C+R | Tab is visible |
| `gdpr` | Boolean | C+R | GDPR confirmed |
| `language` | String | C+R | Browser language |
| `ipaddress` | String | C+R | IP address |
| `heartbeat` | DateTime | C+R | Last heartbeat |

---

## ActivitiesSms

`GET /api/v6/activitiesSms.json`
`GET /api/v6/activitiesSms/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `state` | Enum | R | `ROUTING` or empty |
| `user` | FK→Users | R | |
| `queue` | FK→Queues | C+R | |
| `contact` | FK→Contacts | R | |
| `connector` | FK | R | Connector |
| `sender` | String | R | Phone number |
| `answered` | Boolean | R | |
| `duration` | Time sec | R | |
| `time` | DateTime | R | |
| `wait_time` | Time sec | R | |
| `direction` | Enum | R | `IN` `OUT` (empty=System) |
| `disconnection` | Enum | R+U | `USER` `CLIENT` `TIMEOUT` `NOT_AVAIL` `OUT_OF_TIME` `DECISION_TREE` |
| `missed` | Enum | All | `YES` `NO` |
| `missed_time` | DateTime | All | |
| `options` | Json | C+R | Additional parameters |

---

## ActivitiesFbm

`GET /api/v6/activitiesFbm.json`
`GET /api/v6/activitiesFbm/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `title` | String | C+R | Customer name |
| `state` | Enum | R | `ROUTING` or empty |
| `user` | FK→Users | R | |
| `queue` | FK→Queues | C+R | |
| `contact` | FK→Contacts | R | |
| `connector` | FK | R | Connector |
| `external_contact` | FK | R | External contact |
| `sender` | String | R | Sender ID |
| `answered` | Boolean | R | |
| `duration` | Time sec | R | |
| `time` | DateTime | R | |
| `wait_time` | Time sec | R | |
| `direction` | Enum | R | `IN` `OUT` (empty=System) |
| `disconnection` | Enum | R+U | `USER` `CLIENT` `TIMEOUT` `NOT_AVAIL` `OUT_OF_TIME` `DECISION_TREE` |
| `missed` | Enum | All | `YES` `NO` |
| `missed_time` | DateTime | All | |
| `options` | Json | C+R | Additional parameters |

---

## ActivitiesIgdm

`GET /api/v6/activitiesIgdm.json`
`GET /api/v6/activitiesIgdm/{NAME}.json`

Same fields as ActivitiesFbm, plus:

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `type` | Enum | R | `DM` `STORY_REPLY` `STORY_MENTION` |

---

## ActivitiesWap

`GET /api/v6/activitiesWap.json`
`GET /api/v6/activitiesWap/{NAME}.json`

Same fields as ActivitiesFbm (sender = WhatsApp sender ID, direction `IN`/`OUT`, includes `connector`, `external_contact`, `options`, `missed_time`).

---

## ActivitiesVbr

`GET /api/v6/activitiesVbr.json`
`GET /api/v6/activitiesVbr/{NAME}.json`

Same fields as ActivitiesFbm (sender = Viber sender ID, direction `IN`/`OUT`, includes `connector`, `external_contact`, `options`, `missed_time`).

---

## Contacts

`GET /api/v6/contacts.json`
`GET /api/v6/contacts/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | Unique ID |
| `title` | String | All | Formatted full name |
| `firstname` | String | All | |
| `lastname` | String | All | Required |
| `database` | FK→CrmDatabases | All | Required |
| `account` | FK→Accounts | All | |
| `user` | FK→Users | All | Owner |
| `description` | String | All | |
| `nps_score` | Float | R | Calculated NPS |
| `created` | DateTime | R | |
| `edited` | DateTime | R | |
| `customFields` | Custom | All | |

---

## Accounts

`GET /api/v6/accounts.json`
`GET /api/v6/accounts/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | Unique ID |
| `title` | String | All | Display name (required) |
| `database` | FK→CrmDatabases | All | Required |
| `sla` | FK→TicketsSla | All | |
| `user` | FK→Users | All | Owner |
| `description` | String | All | |
| `created` | DateTime | R | |
| `edited` | DateTime | R | |
| `customFields` | Custom | All | |

---

## CrmRecords

`GET /api/v6/crmRecords.json`
`GET /api/v6/crmRecords/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | Unique ID |
| `type` | FK→CrmRecordsTypes | All | Required |
| `user` | FK→Users | All | Owner |
| `contact` | FK→Contacts | All | |
| `account` | FK→Accounts | All | |
| `ticket` | FK→Tickets | All | |
| `title` | String | All | Required |
| `description` | String | All | |
| `status` | FK→Statuses | All | |
| `stage` | Enum | All | Required. `OPEN` `CLOSE` |
| `created` | DateTime | R | Required |
| `edited` | DateTime | R | |
| `customFields` | Custom | All | |

---

## CampaignsRecords

`GET /api/v6/campaignsRecords.json`
`GET /api/v6/campaignsRecords/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `user` | FK→Users | All | |
| `record_type` | FK→CampaignsTypes | All | Call script (required) |
| `database` | FK→Databases | All | |
| `contact` | FK→Contacts | All | |
| `nextcall` | DateTime | All | Next call date |
| `action` | Enum/Int | All | `0`=Not assigned `1`=Ready `2`=Rescheduled by Dialer `3`=Call in progress `4`=Hangup `5`=Done `6`=Rescheduled |
| `call_id` | String | R | ID of the call |
| `activity` | String | R | Name of the activity |
| `options` | Json | R | Additional parameters |
| `statuses` | MN→Statuses | All | |
| `created` | DateTime | R | |
| `edited` | DateTime | R | |
| `customFields` | Custom | All | |

---

## CampaignsTypes

`GET /api/v6/campaignsTypes.json`
`GET /api/v6/campaignsTypes/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `title` | String | All | Required |
| `description` | String | All | |
| `queue` | FK→Queues | All | |
| `color` | Color | All | |
| `icon` | Enum | All | Icon identifier |
| `autofocused_tab` | String | All | Autofocused tab |
| `config` | Json | All | Options (required) |
| `custom` | Boolean | C+R | Is custom form type |
| `created` | DateTime | R | |

---

## Groups

`GET /api/v6/groups.json`
`GET /api/v6/groups/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `title` | String | All | Required |
| `description` | String | All | |
| `type` | Enum | C+R | Required. `categories` `queues` `users` `profiles` |

---

## Pauses

`GET /api/v6/pauses.json`
`GET /api/v6/pauses/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `title` | String | All | Display name (required) |
| `type` | Enum | R | `wrap` `dnd` `lajdak` (null=Custom pause) |
| `paid` | Boolean | All | |
| `max_duration` | Integer | All | Minutes (0=no limit) |
| `repeatable` | Boolean | All | |
| `max_amount` | Integer | All | Max uses per day |
| `min_timeout` | Integer | All | Minutes between uses |
| `auto_pause` | Boolean | All | |
| `prevent_direct_calls` | Boolean | All | |

---

## Queues

`GET /api/v6/queues.json`
`GET /api/v6/queues/{NAME}.json`

Key fields (queue model has many more configuration fields):

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | Used as `queue` filter in activities |
| `title` | String | All | Display name |
| `type` | Enum | C+R | `in` `out` `email` `chat` `sms` `fbm` `igdm` `wap` `vbr` |

---

## Statuses

`GET /api/v6/statuses.json`
`GET /api/v6/statuses/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `title` | String | All | Required |
| `description` | String | All | |
| `color` | Color | All | |
| `validation` | Boolean | All | |
| `nextcall` | Boolean | All | |

---

## Templates

`GET /api/v6/templates.json`
`GET /api/v6/templates/{NAME}.json`

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | |
| `title` | String | All | Required |
| `description` | String | All | |
| `format` | Enum | All | `RICH` `PLAIN` |
| `usingtype` | Enum | C+R | `EMAIL` `SMS` `FBM` `IGDM` `WAP` `WAP_OUTGOING` `VBR` `CHAT` `CHAT_NPS` `EMAIL_SIGN` `EMAIL_NPS` `SOCIALMEDIA` `USERSIGN` |
| `user` | FK→Users | C+R | Owner (null=visible to all) |
| `subject` | String | All | Email subject |
| `content` | Html | All | |

---

## Users

`GET /api/v6/users.json`
`GET /api/v6/users/{NAME}.json`

Key fields (users model has many more fields):

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `name` | String | C+R | **Login name** — used as `user` filter across all endpoints |
| `title` | String | All | Display name |
| `firstname` | String | All | |
| `lastname` | String | All | |
| `email` | Email | All | |
| `alias` | String | All | |
| `type` | Enum | C+R | `admin` `user` `api` |
| `timezone` | String | All | IANA timezone (e.g. `Europe/Prague`) |

---

## RealtimeSessions

`GET /api/v6/realtimeSessions.json`
(read-only, no single-record endpoint)

| Field | Type | Access | Notes |
|-------|------|--------|-------|
| `id_agent` | FK→Users | R | Agent (login name) |
| `state` | Enum | R | `Session` `Idle` `Paused` |
| `exten` | String | R | Extension |
| `exten_status` | Enum | R | `Unavailable` `Idle` `Busy` |
| `presence_status` | Enum | R | `Unavailable` `Idle` `Busy` |
| `logintime` | DateTime | R | |
| `lastcalltime` | DateTime | R | |
| `lastqueue` | FK→Queues | R | |
| `id_pause` | FK→Pauses | R | Current pause type |
| `onpause` | DateTime | R | When pause started |
| `statetime` | DateTime | R | When entered current state |
| `id_call` | String | R | Active call ID |
| `unwrap` | DateTime | R | Wrap-up end time |
