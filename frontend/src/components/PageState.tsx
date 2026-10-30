import { Alert, Anchor, Center, Loader, Text } from '@mantine/core'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api/client'

export function PageLoader() {
  return (
    <Center p="xl">
      <Loader />
    </Center>
  )
}

export function PageError({ title, error }: { title: string; error: unknown }) {
  return (
    <Alert color="red" title={title}>
      <Text size="sm" mb="xs">
        {errorMessage(error)}
      </Text>
      <Anchor component={Link} to="/" size="sm">
        Back to the queue
      </Anchor>
    </Alert>
  )
}
