# Coding-Agent Experiment Report

## Approach

I treated the supplied agent as an orchestration problem rather than trying to
encode fixes for the ten pytest tasks. The final agent preloads the source files
named in the task and the injected visible test, asks the fixed model for one
structured action at a time, applies only the supplied repository tools, and
runs tests automatically after every write or patch. A failed test result is
then returned to the model for a repair attempt. The model-call budget remains
five and the tool budget remains twelve.

## Iterations

| Iteration | Change | Reason | Cases run and result |
| --- | --- | --- | --- |
| 1 | Kept the starter one-action-per-turn loop | Establish the baseline design and static contract | `check_agent.py`: pass; live case could not start because `openai` was initially missing |
| 2 | Installed the declared requirements | Make the supplied practice runner executable | Requirements installed successfully |
| 3 | Extracted `src/...py` paths from the task | Remove the model's need to discover an explicitly named owner file | Static validation: pass |
| 4 | Pre-read each named source file before the first model call | Give the first call useful implementation context | Static validation: pass |
| 5 | Pre-read `tests/test_task.py` as well | Expose the expected behavior and error wording immediately | Static validation: pass |
| 6 | Reworked the system prompt to require a concrete edit first | Preserve model turns for implementation and repair | Static validation: pass |
| 7 | Preferred exact `patch_file` edits and forbade test changes in the prompt | Reduce accidental broad rewrites and test overfitting | Static validation: pass |
| 8 | Added fenced-JSON tolerant parsing | Recover from a common formatting failure without spending a turn | Static validation: pass |
| 9 | Automatically ran tests after every successful write or patch | Spend the next model call on diagnosis instead of asking it to select `run_tests` | Static validation: pass; compile pass |
| 10 | Fed action errors and test failures back verbatim, and stopped on green tests | Make repair behavior evidence-driven and stop promptly | Static validation: pass; 146 lines, 5,604 bytes |
| 11 | Required a real passing test run before accepting `finish` | Prevent premature success summaries from skipping validation | Static validation, compilation, and fake-interface smoke test: pass |

## Results and limitations

The final agent passes the repository's static checker and Python compilation.
I could not obtain a public-case score in this environment: after installing
`requirements.txt`, the runner stopped before creating a case because
`OPENROUTER_API_KEY` was not available. Therefore the final public score is
**not measured**, rather than being reported as a fabricated pass count. The
same missing-key condition prevented meaningful LLM/tool usage measurements.

The most important expected gains are the initial context packet, automatic
post-edit testing, and explicit failure-driven repair. The main remaining risk
is model variance: some tasks require reading a directly related file not named
in the prompt, and the model must spend one of its remaining turns discovering
that dependency. With a configured key, I would run all ten cases, record
per-case calls and tool usage, inspect every failure, and tune context size or
repair prompting only where the observed failures justified it.
