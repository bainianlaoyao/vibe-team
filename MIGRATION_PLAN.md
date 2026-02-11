# Claude Code UI Migration Plan

## Phase 1: Foundation & Types
- [ ] Install dependencies (markdown-it, DOMPurify)
- [ ] Define TypeScript interfaces (`src/types/chat.ts`) for Messages, ToolInvocations, and StreamEvents.
- [ ] Setup Pinia Store (`src/stores/chat.ts`) for managing message history and tool confirmation states.

## Phase 2: Leaf Components (The "Look")
- [ ] `components/chat/ThinkingBlock.vue`: Collapsible "Thinking..." block.
- [ ] `components/chat/ToolCallBlock.vue`: The signature black card showing tool execution status (Running/Completed).
- [ ] `components/chat/MarkdownBlock.vue`: Safe Markdown rendering.

## Phase 3: Composite Components (The "Flow")
- [ ] `components/chat/MessageItem.vue`: The hybrid renderer that switches between Text and Tool blocks.
- [ ] `components/chat/ToolConfirmation.vue`: The "Human-in-the-loop" interceptor (Y/N dialog).
- [ ] `components/chat/ChatInput.vue`: Auto-expanding input with command support.

## Phase 4: Integration
- [ ] `views/ChatInterface.vue`: Main container assembling all parts.
- [ ] Mock Service: A simple simulator to generate stream events for testing UI states.

