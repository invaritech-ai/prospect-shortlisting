export interface QueryRequestToken {
  key: string
  sequence: number
}

export function createQueryRequestGate() {
  let nextSequence = 0
  const latestSequenceByKey = new Map<string, number>()

  return {
    start(key: string): QueryRequestToken {
      nextSequence += 1
      latestSequenceByKey.set(key, nextSequence)
      return { key, sequence: nextSequence }
    },

    isCurrent(token: QueryRequestToken, currentKey: string): boolean {
      return token.key === currentKey && latestSequenceByKey.get(token.key) === token.sequence
    },
  }
}
