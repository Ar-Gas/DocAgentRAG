export const extractQueryTerms = (query = '') => {
  if (!query || !query.trim()) {
    return []
  }

  const terms = query
    .split(/[\s,，。；;、]+/)
    .map((item) => item.trim())
    .filter(Boolean)

  return [...new Set(terms)].sort((left, right) => right.length - left.length)
}

export const buildSegmentsFromRanges = (text = '', ranges = [], isActiveRange = () => false) => {
  if (!text) {
    return []
  }

  const sortedRanges = [...ranges]
    .filter((item) => Number.isInteger(item.start) && Number.isInteger(item.end) && item.end > item.start)
    .sort((left, right) => {
      if (left.start !== right.start) {
        return left.start - right.start
      }
      return right.end - left.end
    })

  const mergedRanges = []
  for (const range of sortedRanges) {
    const previous = mergedRanges[mergedRanges.length - 1]
    if (previous && range.start < previous.end) {
      continue
    }
    mergedRanges.push(range)
  }

  if (!mergedRanges.length) {
    return [{ key: 'plain-0', text, highlight: false, active: false }]
  }

  const segments = []
  let cursor = 0

  mergedRanges.forEach((range, index) => {
    if (range.start > cursor) {
      segments.push({
        key: `plain-${index}-${cursor}`,
        text: text.slice(cursor, range.start),
        highlight: false,
        active: false
      })
    }

    segments.push({
      key: range.key || `mark-${index}-${range.start}-${range.end}`,
      text: text.slice(range.start, range.end),
      highlight: true,
      active: isActiveRange(range),
      term: range.term
    })
    cursor = range.end
  })

  if (cursor < text.length) {
    segments.push({
      key: `plain-tail-${cursor}`,
      text: text.slice(cursor),
      highlight: false,
      active: false
    })
  }

  return segments
}

export const buildSegmentsFromQuery = (text = '', query = '') => {
  const terms = extractQueryTerms(query)
  if (!terms.length) {
    return [{ key: 'plain-0', text, highlight: false, active: false }]
  }

  const ranges = []
  terms.forEach((term, termIndex) => {
    const matcher = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
    Array.from(text.matchAll(matcher)).forEach((match, matchIndex) => {
      ranges.push({
        key: `query-${termIndex}-${matchIndex}-${match.index}`,
        start: match.index,
        end: match.index + match[0].length,
        term
      })
    })
  })

  return buildSegmentsFromRanges(text, ranges)
}
