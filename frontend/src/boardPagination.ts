export const PAGE_SIZE = 20
const MAX_PAGE_SIZE = 100

export async function loadBoardWindow<T>(
  count: number,
  fetchPage: (limit: number, cursor: number | null) => Promise<{ items: T[]; next: number | null }>,
) {
  const items: T[] = []
  let next: number | null = null
  do {
    const page = await fetchPage(Math.min(count - items.length, MAX_PAGE_SIZE), next)
    items.push(...page.items)
    next = page.next
  } while (next !== null && items.length < count)
  return { items, next }
}
