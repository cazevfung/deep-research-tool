import React from 'react'
import { LiveGoal } from '../../stores/workflowStore'

interface ResearchGoalListProps {
  goals: LiveGoal[]
}

const classNames = (...classes: Array<string | false | null | undefined>) => classes.filter(Boolean).join(' ')

const statusLabelMap: Record<LiveGoal['status'], string> = {
  pending: '等待',
  streaming: '生成中',
  ready: '已就绪',
  error: '错误',
}

const ResearchGoalList: React.FC<ResearchGoalListProps> = ({ goals }) => {
  if (!goals || goals.length === 0) {
    return null
  }

  return (
    <section aria-label="研究目标列表" className="space-y-4">
      <header className="flex flex-col gap-1">
        <h4 className="text-base font-semibold text-neutral-800">共 {goals.length} 项研究目标</h4>
        <p className="text-sm text-neutral-500">
          目标以清单形式展示，可实时查看生成进度与重点字段。
        </p>
      </header>

      <ul className="space-y-3" role="list">
        {goals.map((goal, index) => {
          const status = goal.status || 'ready'
          const isLoading = status === 'pending' || status === 'streaming'
          const goalId = goal.id ?? index + 1
          const titleId = `goal-${goalId}-title`

          return (
            <li
              key={goalId}
              className={classNames(
                'group rounded-2xl border border-neutral-200 bg-neutral-white/90 p-5 shadow-sm transition focus-within:border-primary-300',
                status === 'ready' && 'hover:border-primary-200 hover:shadow-md',
                isLoading && 'border-dashed opacity-85',
                status === 'error' && 'border-red-200 bg-red-50/70'
              )}
            >
              <article className="flex flex-col gap-4" aria-labelledby={titleId}>
                <header className="flex items-start gap-4">
                  <div
                    className={classNames(
                      'flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
                      status !== 'error' && 'bg-primary-100 text-primary-700',
                      status === 'error' && 'bg-red-200 text-red-800'
                    )}
                  >
                    {goalId}
                  </div>
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      <h5
                        id={titleId}
                        className={classNames(
                          'text-base font-semibold leading-relaxed',
                          status !== 'error' && 'text-neutral-900',
                          status === 'error' && 'text-red-800'
                        )}
                      >
                        {goal.goal_text || '正在生成研究目标…'}
                      </h5>
                      <span
                        className={classNames(
                          'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                          status === 'ready' && 'bg-primary-100 text-primary-700',
                          status === 'streaming' && 'bg-amber-100 text-amber-700 animate-pulse',
                          status === 'pending' && 'bg-neutral-100 text-neutral-500',
                          status === 'error' && 'bg-red-100 text-red-700'
                        )}
                      >
                        {statusLabelMap[status]}
                      </span>
                    </div>

                    {goal.rationale && (
                      <p className="text-sm text-neutral-600">
                        {goal.rationale}
                      </p>
                    )}

                    {isLoading && !goal.rationale && (
                      <p className="text-sm text-neutral-400">
                        正在补充背景说明…
                      </p>
                    )}

                  </div>
                </header>

                {isLoading && (
                  <div className="flex items-center gap-2 text-xs text-neutral-400">
                    <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-primary-400" aria-hidden="true" />
                    正在解析并完善此目标…
                  </div>
                )}
              </article>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

export default ResearchGoalList
