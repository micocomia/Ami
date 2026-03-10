# API Endpoints

Each endpoint module follows the same structure so pages can import and call them consistently.

## Pattern (per endpoint or per group)

1. **Types** — Re-export or define `XxxRequest` and `XxxResponse` (from `@/types` or inline).
2. **Zod schema** (optional) — `xxxRequestSchema` / `xxxResponseSchema` for runtime validation.
3. **API function** — `xxxApi(params): Promise<XxxResponse>` using `apiClient` (axios).
4. **React Query hook** — `useXxx()` that uses `useQuery` or `useMutation` and calls the api function.

## Naming

- **Types**: `XxxRequest`, `XxxResponse`
- **Api function**: `xxxApi` (camelCase)
- **Hook**: `useXxx` (PascalCase)
- **Query keys**: `xxxKeys` (e.g. `authKeys.me`, `refineLearningGoalKeys.all`)

## Files

- **auth.ts** — register, login, me, deleteUser
- **config.ts** — appConfig, personas, llmModels
- **userState.ts** — getUserState, putUserState, deleteUserState
- **profile.ts** — getProfile, putProfile, syncProfile, autoUpdateProfile
- **events.ts** — logEvent, getEvents
- **metrics.ts** — getBehavioralMetrics, getQuizMix, getSessionMasteryStatus
- **mastery.ts** — evaluateMastery
- **learningPath.ts** — scheduleLearningPath, rescheduleLearningPath, scheduleAgentic, adaptLearningPath
- **pdf.ts** — extractPdfText
- **refineLearningGoal.ts** — refineLearningGoal (includes Zod example)

## Example usage (page)

```tsx
import { useRefineLearningGoal, refineLearningGoalRequestSchema } from '@/api/endpoints/refineLearningGoal';

const { mutate, data, isPending, error } = useRefineLearningGoal();
// Optional: refineLearningGoalRequestSchema.safeParse(payload) before mutate(payload)
mutate({ learning_goal: '...', learner_information: '...' });
```

See `src/pages/RefineGoalExamplePage.tsx` for a full example.
