# Why Freshdocs Exists

Agents make developers fast until they use stale APIs with confidence.

The expensive failure is not "the agent did not know." The expensive failure is that the agent sounded certain, generated plausible code, and pushed the human into debugging false context.

Freshdocs attacks that failure directly:

- current version facts
- official source snippets
- changelog awareness
- local cache
- small context packs
- explicit stale state

## Will Hierarchy

Highest will: ship correct code faster without surrendering control.

Lower wills:

- avoid checking docs manually
- avoid embarrassing build failures
- avoid cloud dependency for private work
- avoid prompt bloat
- avoid tool lock-in

Conflict:

- "Always latest" can create network dependence and noise.
- "Always local" can become stale.

Resolution:

- sync deliberately
- show checked date
- route only relevant snippets into the prompt
- make stale visible

## Human Driver

The user should feel:

- safer because the agent is grounded
- faster because docs are already packed
- in control because everything is local and inspectable
- competent because fewer API mistakes escape into code

