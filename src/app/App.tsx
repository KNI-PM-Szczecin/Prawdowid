import { texts } from './lib/texts'

function App() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 px-4 py-16 text-black">
      <h1 className="text-3xl font-semibold">{texts.appName}</h1>
      <p className="text-lg">{texts.tagline}</p>
    </main>
  )
}

export default App
