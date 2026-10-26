# Arquitectura

## Componentes

```mermaid
flowchart LR
    subgraph Fuentes
        W[Wikimedia Pageviews API]
        G[CSV Google Trends]
        P[PyTrends - opcional]
    end
    subgraph Backend
        WK[Worker programado]
        DB[(PostgreSQL)]
        API[API REST - FastAPI]
        DET[Detector de picos]
    end
    UI[Dashboard - Streamlit]
    W --> WK
    P --> WK
    G -.carga manual.-> DB
    WK --> DB
    DB --> API
    API --> DET
    API --> UI
```

La configuración Docker Compose define cinco servicios: base de datos, API principal, API externa simulada, worker y dashboard.

## UML de clases (simplificado)

```mermaid
classDiagram
    class Connector {
        <<abstract>>
        +name: str
        +fetch(term, start, end) list~Point~
    }
    class WikipediaConnector
    class PyTrendsConnector
    class Point {
        +date
        +value
    }
    class Keyword {
        +id
        +term
        +created_at
    }
    class Observation {
        +id
        +source
        +date
        +value
    }
    class SpikeResult {
        +is_spike
        +z_score
        +growth
    }
    Connector <|-- WikipediaConnector
    Connector <|-- PyTrendsConnector
    Connector ..> Point : produce
    Keyword "1" --> "*" Observation
    Observation ..> SpikeResult : detect_spike()
```

## Flujo de una consulta de pico

```mermaid
sequenceDiagram
    participant U as Usuario
    participant A as API
    participant D as BD
    participant S as Detector
    U->>A: GET /trends/{term}/spike
    A->>D: serie de observaciones
    D-->>A: valores diarios
    A->>S: detect_spike(serie)
    S-->>A: z-score, crecimiento, is_spike
    A-->>U: JSON
```

## Decisiones técnicas

| Decisión | Motivo |
|---|---|
| Conectores con interfaz común | Cambiar o añadir fuentes sin tocar el resto del sistema |
| z-score sobre media móvil de 28 días | Método simple, explicable y validable con backtest |
| FastAPI | Documentación OpenAPI automática y tipado |
| PostgreSQL en Docker (SQLite en local) | Mismo código, entorno de desarrollo sin fricción |
| Worker separado de la API | La ingesta (lenta, falla a veces) no afecta a la API |
| Docker + CI | Reproducibilidad y despliegue en cualquier proveedor de nube |

## Despliegue en la nube (por decidir)
El proveedor y el servicio (VM con docker-compose, o servicio de contenedores gestionado) están
pendientes de decisión del equipo / profesor. La arquitectura no depende de ninguno concreto.
