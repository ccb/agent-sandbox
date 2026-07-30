# Believability audit

- Run: `godot-generative-agents/runs/run-20260730-025718-889dac` -- 4320 steps, 5 personas
- Judge: llm (anthropic/claude-haiku-4-5), 10 calls, $0.1576 spent (ceiling $1.00)

## Run summary

| Dimension | Mean score |
| --- | --- |
| Plan coherence | 6.46/10 |
| Temporal sanity | 8.5/10 |
| Social grounding | 8.2/10 |
| World grounding | 10/10 |
| Memory use | 9.88/10 |
| **Overall** | **8.61/10** |
| Weakest agent | Maya Chen (8.02/10) |

## Professor Tanaka

Overall: **9.78/10**

### Plan coherence: 10/10
_model declined or replied malformed; heuristic score (reached 2 of 2 planned stops in order; 100% of matched segments in plan order)_
- steps 0-70 (08:00): 'walking to Irvine Auditorium @ UPenn:Irvine Auditorium:lobby' matches stop 1 'setting up for the 10:00 guest lecture on gravitational waves at Irvine Auditorium'
- steps 71-430 (08:11): 'checking av equipment @ UPenn:Irvine Auditorium:lobby' matches stop 1 'setting up for the 10:00 guest lecture on gravitational waves at Irvine Auditorium'

### Temporal sanity: 9.9/10
_model declined or replied malformed; heuristic score (activity churn 0%; schedule-window fit 100%)_
- 19 activity stretches over 4320 steps (a coherent day changes activity rarely)
- 100% of planned activity falls inside its scheduled time window

### Social grounding: 9/10
_model declined or replied malformed; heuristic score (4 conversation(s) checked)_
- steps 819-910 (10:16): conversation between Professor Tanaka, Theo Lindqvist -- co-located 100% of the window, 3/3 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 911-1095 (10:31): conversation between Professor Tanaka, Theo Lindqvist -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 84% of its words new to this pair
- steps 1096-1275 (11:02): conversation between Professor Tanaka, Theo Lindqvist -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 67% of its words new to this pair
- steps 1276-4319 (11:32): conversation between Mateo Vasquez, Professor Tanaka -- co-located 3% of the window, 5/5 substantive lines grounded in both streams, 100% of its words new to this pair

### World grounding: 10/10
_model declined or replied malformed; heuristic score (4 conversation window(s) checked against 18 real place(s))_
- steps 819-910 (10:16): no place words seen; 2 line(s) of Professor Tanaka checked
- steps 911-1095 (10:31): no place words seen; 3 line(s) of Professor Tanaka checked
- steps 1096-1275 (11:02): no place words seen; 3 line(s) of Professor Tanaka checked
- steps 1276-4319 (11:32): no place words seen; 3 line(s) of Professor Tanaka checked

### Memory use: 10/10
_model declined or replied malformed; heuristic score (20/20 decisions used a relevant memory)_
- step 0 (08:00): retrieved 'Plan: go to Irvine Auditorium and setting up for the 10:00 guest lecture on gravitational waves. Today's stops: setting up for the 10:00 guest lecture on gravitational waves at Irvine Auditorium, then holding a problem session for her physics class at Williams Hall — Classroom A.' while 'walking to Irvine Auditorium @ UPenn:Irvine Auditorium:lobby'
- step 71 (08:11): retrieved 'I traveled to Irvine Auditorium.' while 'checking av equipment @ UPenn:Irvine Auditorium:lobby'

## Maya Chen

Overall: **8.02/10**

### Plan coherence: 3.5/10
_model declined or replied malformed; heuristic score (reached 3 of 6 planned stops in order; 55% of matched segments in plan order)_
- steps 120-227 (08:20): 'walking to Van Pelt — Moelis Reading Room @ UPenn:Van Pelt Library:Moelis Family Grand Reading Room' matches stop 2 'studying for an organic chemistry exam at Van Pelt — Moelis Reading Room'
- steps 228-574 (08:38): 'walking to Houston Hall @ UPenn:Houston Hall:lobby' matches stop 3 'grabbing a coffee at the student union at Houston Hall'
- steps 0-119 (08:00): 'spending time @ None' matches no schedule stop

### Temporal sanity: 8.6/10
_model declined or replied malformed; heuristic score (activity churn 0%; schedule-window fit 70%)_
- 12 activity stretches over 4320 steps (a coherent day changes activity rarely)
- steps 1030-1373 (10:51): 'walking to Van Pelt — Moelis Reading Room @ UPenn:Van Pelt Library:Moelis Family Grand Reading Room' happens far outside its scheduled window
- steps 1374-1463 (11:49): 'sipping coffee and reviewing orgo problem set with priya @ UPenn:Van Pelt Library:Moelis Family Grand Reading Room' happens far outside its scheduled window
- 70% of planned activity falls inside its scheduled time window

### Social grounding: 8/10
_model declined or replied malformed; heuristic score (9 conversation(s) checked)_
- steps 0-664 (08:00): conversation between Maya Chen, Priya Nair -- co-located 28% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 575-818 (09:35): conversation between Maya Chen, Theo Lindqvist -- co-located 41% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 665-849 (09:50): conversation between Maya Chen, Priya Nair -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 66% of its words new to this pair
- steps 850-1373 (10:21): conversation between Maya Chen, Priya Nair -- co-located 20% of the window, 6/6 substantive lines grounded in both streams, 47% of its words new to this pair
- steps 1374-2025 (11:49): conversation between Maya Chen, Priya Nair -- co-located 49% of the window, 6/6 substantive lines grounded in both streams, 69% of its words new to this pair
- steps 1589-1773 (12:24): conversation between Maya Chen, Theo Lindqvist -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 74% of its words new to this pair
- steps 1774-2048 (12:55): conversation between Maya Chen, Theo Lindqvist -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 71% of its words new to this pair
- steps 2049-4319 (13:41): conversation between Maya Chen, Theo Lindqvist -- co-located 6% of the window, 6/6 substantive lines grounded in both streams, 57% of its words new to this pair
- steps 3158-4319 (16:46): conversation between Mateo Vasquez, Maya Chen -- co-located 9% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair

### World grounding: 10/10
_model declined or replied malformed; heuristic score (9 conversation window(s) checked against 18 real place(s))_
- steps 0-664 (08:00): no place words seen; 3 line(s) of Maya Chen checked
- steps 575-818: mentions lab (not in this world) without claiming to have been there -- allowed, not scored
- steps 665-849 (09:50): no place words seen; 3 line(s) of Maya Chen checked
- steps 850-1373 (10:21): no place words seen; 3 line(s) of Maya Chen checked
- steps 1374-2025 (11:49): no place words seen; 3 line(s) of Maya Chen checked
- steps 1589-1773: mentions track (not in this world) without claiming to have been there -- allowed, not scored
- steps 1774-2048 (12:55): no place words seen; 3 line(s) of Maya Chen checked
- steps 2049-4319 (13:41): no place words seen; 3 line(s) of Maya Chen checked
- steps 3158-4319: mentions track (not in this world) without claiming to have been there -- allowed, not scored

### Memory use: 10/10
_model declined or replied malformed; heuristic score (18/18 decisions used a relevant memory)_
- step 0 (08:00): retrieved 'Plan: go to Van Pelt — Circulation Desk and checking out a reserved organic chemistry textbook. Today's stops: checking out a reserved organic chemistry textbook at Van Pelt — Circulation Desk, then studying for an organic chemistry exam at Van Pelt — Moelis Reading Room, then grabbing a coffee at the student union at Houston Hall, then heading to a seminar at College Hall, then pulling a few references off the shelves at Van Pelt — Book Stacks, then reviewing her notes before tomorrow at Van Pelt — Study Booths.' while 'spending time @ None'
- step 90 (08:15): retrieved 'Priya Nair did: talk_to Maya Chen about heading to Moelis Reading Room to start the problem set' while 'spending time @ None'

## Priya Nair

Overall: **8.02/10**

### Plan coherence: 5.1/10
_model declined or replied malformed; heuristic score (reached 3 of 4 planned stops in order; 61% of matched segments in plan order)_
- steps 90-190 (08:15): 'walking to Van Pelt — Circulation Desk @ UPenn:Van Pelt Library:Circulation' matches stop 1 'working through a problem set with Maya at Van Pelt — Moelis Reading Room'
- steps 191-250 (08:31): 'asking the circulation desk staff for the reserved orgo textbook @ UPenn:Van Pelt Library:Circulation' matches stop 1 'working through a problem set with Maya at Van Pelt — Moelis Reading Room'
- steps 0-89 (08:00): 'spending time @ None' matches no schedule stop

### Temporal sanity: 7.3/10
_model declined or replied malformed; heuristic score (activity churn 1%; schedule-window fit 43%)_
- 24 activity stretches over 4320 steps (a coherent day changes activity rarely)
- steps 940-1291 (10:36): 'walking to Van Pelt — Moelis Reading Room @ UPenn:Van Pelt Library:Moelis Family Grand Reading Room' happens far outside its scheduled window
- steps 1292-1321 (11:35): 'grabbing coffee at the counter and chatting with maya about the textbook mixup @ UPenn:Van Pelt Library:Moelis Family Grand Reading Room' happens far outside its scheduled window
- 43% of planned activity falls inside its scheduled time window

### Social grounding: 7.7/10
_model declined or replied malformed; heuristic score (7 conversation(s) checked)_
- steps 0-664 (08:00): conversation between Maya Chen, Priya Nair -- co-located 28% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 665-849 (09:50): conversation between Maya Chen, Priya Nair -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 66% of its words new to this pair
- steps 850-1373 (10:21): conversation between Maya Chen, Priya Nair -- co-located 20% of the window, 6/6 substantive lines grounded in both streams, 47% of its words new to this pair
- steps 1374-2025 (11:49): conversation between Maya Chen, Priya Nair -- co-located 49% of the window, 6/6 substantive lines grounded in both streams, 69% of its words new to this pair
- steps 2026-2120 (13:37): conversation between Mateo Vasquez, Priya Nair -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 2121-2644 (13:53): conversation between Mateo Vasquez, Priya Nair -- co-located 19% of the window, 5/5 substantive lines grounded in both streams, 47% of its words new to this pair
- steps 2645-4319 (15:20): conversation between Mateo Vasquez, Priya Nair -- co-located 9% of the window, 5/5 substantive lines grounded in both streams, 60% of its words new to this pair

### World grounding: 10/10
_model declined or replied malformed; heuristic score (7 conversation window(s) checked against 18 real place(s))_
- steps 0-664 (08:00): no place words seen; 3 line(s) of Priya Nair checked
- steps 665-849 (09:50): no place words seen; 3 line(s) of Priya Nair checked
- steps 850-1373 (10:21): no place words seen; 3 line(s) of Priya Nair checked
- steps 1374-2025 (11:49): no place words seen; 3 line(s) of Priya Nair checked
- steps 2026-2120 (13:37): no place words seen; 3 line(s) of Priya Nair checked
- steps 2121-2644 (13:53): no place words seen; 3 line(s) of Priya Nair checked
- steps 2645-4319 (15:20): no place words seen; 3 line(s) of Priya Nair checked

### Memory use: 10/10
_model declined or replied malformed; heuristic score (32/32 decisions used a relevant memory)_
- step 0 (08:00): retrieved 'Plan: go to Van Pelt — Moelis Reading Room and working through a problem set with Maya. Today's stops: working through a problem set with Maya at Van Pelt — Moelis Reading Room, then grabbing lunch between classes at Houston Hall, then pulling a dataset for a course project at Van Pelt — Digital Scholarship Exchange, then heading to a lecture at College Hall.' while 'spending time @ None'
- step 90 (08:15): retrieved 'Maya Chen did: talk_to Priya Nair about morning plans / heading to Van Pelt to grab the reserved orgo textbook' while 'walking to Van Pelt — Circulation Desk @ UPenn:Van Pelt Library:Circulation'

## Theo Lindqvist

Overall: **8.12/10**

### Plan coherence: 5.5/10
_model declined or replied malformed; heuristic score (reached 3 of 6 planned stops in order; 100% of matched segments in plan order)_
- steps 0-43 (08:00): 'walking to Houston Hall @ UPenn:Houston Hall:lobby' matches stop 1 'surfacing for brunch long after sunrise at Houston Hall'
- steps 44-664 (08:07): 'spending time @ UPenn:Houston Hall:lobby' matches stop 1 'surfacing for brunch long after sunrise at Houston Hall'
- steps 665-818 (09:50): 'walking to Irvine Auditorium @ UPenn:Irvine Auditorium:lobby' matches no schedule stop

### Temporal sanity: 7/10
_model declined or replied malformed; heuristic score (activity churn 0%; schedule-window fit 35%)_
- 11 activity stretches over 4320 steps (a coherent day changes activity rarely)
- steps 1276-1588 (11:32): 'walking to Van Pelt — Moelis Reading Room @ UPenn:Van Pelt Library:Moelis Family Grand Reading Room' happens far outside its scheduled window
- steps 1589-1948 (12:24): 'studying annotating readings @ UPenn:Van Pelt Library:Moelis Family Grand Reading Room' happens far outside its scheduled window
- 35% of planned activity falls inside its scheduled time window

### Social grounding: 8.7/10
_model declined or replied malformed; heuristic score (8 conversation(s) checked)_
- steps 575-818 (09:35): conversation between Maya Chen, Theo Lindqvist -- co-located 41% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 819-910 (10:16): conversation between Professor Tanaka, Theo Lindqvist -- co-located 100% of the window, 3/3 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 911-1095 (10:31): conversation between Professor Tanaka, Theo Lindqvist -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 84% of its words new to this pair
- steps 1096-1275 (11:02): conversation between Professor Tanaka, Theo Lindqvist -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 67% of its words new to this pair
- steps 1186-1588 (11:17): conversation between Mateo Vasquez, Theo Lindqvist -- co-located 26% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 1589-1773 (12:24): conversation between Maya Chen, Theo Lindqvist -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 74% of its words new to this pair
- steps 1774-2048 (12:55): conversation between Maya Chen, Theo Lindqvist -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 71% of its words new to this pair
- steps 2049-4319 (13:41): conversation between Maya Chen, Theo Lindqvist -- co-located 6% of the window, 6/6 substantive lines grounded in both streams, 57% of its words new to this pair

### World grounding: 10/10
_model declined or replied malformed; heuristic score (8 conversation window(s) checked against 18 real place(s))_
- steps 575-818: mentions lab (not in this world) without claiming to have been there -- allowed, not scored
- steps 819-910 (10:16): no place words seen; 1 line(s) of Theo Lindqvist checked
- steps 911-1095 (10:31): no place words seen; 3 line(s) of Theo Lindqvist checked
- steps 1096-1275 (11:02): no place words seen; 3 line(s) of Theo Lindqvist checked
- steps 1186-1588 (11:17): no place words seen; 3 line(s) of Theo Lindqvist checked
- steps 1589-1773: mentions track (not in this world) without claiming to have been there -- allowed, not scored
- steps 1774-2048 (12:55): no place words seen; 3 line(s) of Theo Lindqvist checked
- steps 2049-4319 (13:41): no place words seen; 3 line(s) of Theo Lindqvist checked

### Memory use: 9.4/10
_model declined or replied malformed; heuristic score (13/14 decisions used a relevant memory)_
- step 0 (08:00): retrieved 'Plan: go to Houston Hall and surfacing for brunch long after sunrise. Today's stops: surfacing for brunch long after sunrise at Houston Hall, then annotating a stack of philosophy papers at Van Pelt — Moelis Reading Room, then arguing footnotes with anyone who sits down at Houston Hall — Reading Room, then drafting a seminar paper in a corner booth at Van Pelt — Study Booths, then hunting down one elusive citation at Van Pelt — Book Stacks, then writing deep into the quiet hours at Van Pelt — Study Booths.' while 'walking to Houston Hall @ UPenn:Houston Hall:lobby'
- step 44 (08:07): retrieved 'I see apple nearby.' while 'spending time @ UPenn:Houston Hall:lobby'
- step 665 (09:50): none of the 6 retrieved memories relate to 'walking to Irvine Auditorium @ UPenn:Irvine Auditorium:lobby'

## Mateo Vasquez

Overall: **9.1/10**

### Plan coherence: 8.2/10
_model declined or replied malformed; heuristic score (reached 2 of 2 planned stops in order; 80% of matched segments in plan order)_
- steps 0-48 (08:00): 'walking to College Hall @ UPenn:College Hall:lobby' matches stop 1 'trailing an older sibling around at College Hall'
- steps 49-104 (08:08): 'walking to Houston Hall — Reception Hall @ UPenn:Houston Hall:Reception Hall' matches stop 2 'finding his feet at the union at Houston Hall'
- steps 993-1138 (10:45): 'walking to Irvine Auditorium @ UPenn:Irvine Auditorium:lobby' matches no schedule stop

### Temporal sanity: 9.7/10
_model declined or replied malformed; heuristic score (activity churn 1%; schedule-window fit 95%)_
- 24 activity stretches over 4320 steps (a coherent day changes activity rarely)
- steps 4157-4319 (19:32): 'looking around for elena to regroup for dinner @ UPenn:Houston Hall:lobby' happens far outside its scheduled window
- 95% of planned activity falls inside its scheduled time window

### Social grounding: 7.6/10
_model declined or replied malformed; heuristic score (6 conversation(s) checked)_
- steps 1186-1588 (11:17): conversation between Mateo Vasquez, Theo Lindqvist -- co-located 26% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 1276-4319 (11:32): conversation between Mateo Vasquez, Professor Tanaka -- co-located 3% of the window, 5/5 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 2026-2120 (13:37): conversation between Mateo Vasquez, Priya Nair -- co-located 100% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair
- steps 2121-2644 (13:53): conversation between Mateo Vasquez, Priya Nair -- co-located 19% of the window, 5/5 substantive lines grounded in both streams, 47% of its words new to this pair
- steps 2645-4319 (15:20): conversation between Mateo Vasquez, Priya Nair -- co-located 9% of the window, 5/5 substantive lines grounded in both streams, 60% of its words new to this pair
- steps 3158-4319 (16:46): conversation between Mateo Vasquez, Maya Chen -- co-located 9% of the window, 6/6 substantive lines grounded in both streams, 100% of its words new to this pair

### World grounding: 10/10
_model declined or replied malformed; heuristic score (6 conversation window(s) checked against 18 real place(s))_
- steps 1186-1588 (11:17): no place words seen; 3 line(s) of Mateo Vasquez checked
- steps 1276-4319 (11:32): no place words seen; 2 line(s) of Mateo Vasquez checked
- steps 2026-2120 (13:37): no place words seen; 3 line(s) of Mateo Vasquez checked
- steps 2121-2644 (13:53): no place words seen; 2 line(s) of Mateo Vasquez checked
- steps 2645-4319 (15:20): no place words seen; 2 line(s) of Mateo Vasquez checked
- steps 3158-4319: mentions track (not in this world) without claiming to have been there -- allowed, not scored

### Memory use: 10/10
_model declined or replied malformed; heuristic score (35/35 decisions used a relevant memory)_
- step 0 (08:00): retrieved 'Plan: go to College Hall and trailing an older sibling around. Today's stops: trailing an older sibling around at College Hall, then finding his feet at the union at Houston Hall.' while 'walking to College Hall @ UPenn:College Hall:lobby'
- step 49 (08:08): retrieved 'I traveled to College Hall.' while 'walking to Houston Hall — Reception Hall @ UPenn:Houston Hall:Reception Hall'
