export default function LineItemsTable({
  items,
}: {
  items?: Array<{
    item_id: string
    description: string
    quantity: string | number
    unit_price: string | number
    line_total: string | number
  }>
}) {
  if (!items?.length) {
    return <p className="text-sm text-slate-500">No line items were returned.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="table table-sm">
        <thead>
          <tr>
            <th>Description</th>
            <th>Qty</th>
            <th>Unit</th>
            <th>Line total</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.item_id}>
              <td>{item.description}</td>
              <td>{String(item.quantity)}</td>
              <td>{String(item.unit_price)}</td>
              <td>{String(item.line_total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
