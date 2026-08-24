# Connectivity test design contract

## Intent

- Product and user: a temporary server visibility and bidirectional connectivity test for the server operator.
- Primary tasks: confirm the page is reachable, read the current local time, exchange messages between browsers and a terminal tool.
- Desired qualities: immediate, calm, technical, legible, responsive.
- Rejected qualities: decorative gradients, generic dashboard cards, excessive glow, hidden connection state, dependency-heavy styling.
- Direction: Monochrome Precision (S5), because connection state and time need crisp hierarchy with minimal visual noise.
- Borrowed trait: the restrained, full-width message composition from S7; messages use dividers instead of chat bubbles.

## Foundations

- Typography: system UI sans for interface text and system monospace for tabular time. Scale is 10, 11, 12, 13, 14, 18, and a fluid 64–136 px clock.
- Colors: near-black background, graphite chat surface, off-white primary text, cool gray secondary text, green only for healthy/primary state, red only for errors.
- Spacing: 4, 8, 12, 16, 24, and 32 px.
- Radius hierarchy: 6 px inputs, 10 px actions, 16 px containing panel.
- Borders/elevation: one-pixel separators; one shadow only on the desktop chat panel.
- Imagery/icons/data visualization: none required for this diagnostic tool.

## Layout gramma

- Wide desktop: the clock is centered in the available stage; a fixed 368 px conversation panel occupies the right edge.
- Compact desktop/tablet: the clock becomes a 56 vh top section and chat moves into document flow.
- Mobile under 520 px: chat becomes a full-width bottom region with no horizontal scrolling.
- Message scrolling is owned by the message list on desktop and within the bounded chat region on small screens.

## Components and states

- Health indicator: checking, online, and error states include text and a dot so color is not the sole signal.
- Conversation: empty state, history, incoming live message, long wrapping content, and reconnection feedback.
- Composer: named input, required message input, focus, hover, pressed, disabled/sending, success, and error states.
- Inputs use native keyboard behavior and visible labels; the message feed uses a polite live region.

## Motion and validation

- Functional transitions use 120 ms color/press feedback; reduced-motion mode removes them.
- Reference widths: 1440 px desktop, 768 px tablet, and 390 px mobile.
- Required scene: conversation and composer, including empty, populated, reconnecting, sending, success, and error states.
- Checks: keyboard focus, contrast, long messages, no overflow, and readable clock digits.
