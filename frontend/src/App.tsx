import { Center, Text } from '@mantine/core'
import { Route, Routes } from 'react-router-dom'

export function App() {
  return (
    <Routes>
      <Route
        path="*"
        element={
          <Center h="100vh">
            <Text>BOM System</Text>
          </Center>
        }
      />
    </Routes>
  )
}
