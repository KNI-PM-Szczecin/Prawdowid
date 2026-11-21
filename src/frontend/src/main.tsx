import { render } from "preact";
import "@fontsource/prompt/400.css";
import "@fontsource/prompt/500.css";
import "@fontsource/prompt/600.css";
import "./styles/global.scss";
import { App } from "./App.tsx";

render(<App />, document.getElementById("app")!);
