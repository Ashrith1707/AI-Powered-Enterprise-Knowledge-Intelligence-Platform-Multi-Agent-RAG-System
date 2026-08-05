import { Hammer } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/States'
import { Card } from '@/components/ui/card'

/** Temporary stub for modules not yet rebuilt in the new design system. */
export default function PlaceholderPage({ title, description, note }) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      <Card>
        <EmptyState
          icon={Hammer}
          title="This module is queued for the redesign"
          hint={note ?? 'Confirm the next module and it will be built here.'}
        />
      </Card>
    </div>
  )
}
