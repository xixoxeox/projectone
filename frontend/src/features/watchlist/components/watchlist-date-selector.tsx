export function WatchlistDateSelector({ dates, selected, onSelect }: { dates: string[]; selected: string; onSelect: (date: string) => void }) {
  return <div className="date-selector"><label htmlFor="watchlist-date">조회 날짜</label><select id="watchlist-date" value={selected} onChange={(event) => onSelect(event.target.value)}>{dates.map(date => <option key={date} value={date}>{date}</option>)}</select></div>;
}
