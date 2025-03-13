# EnvHero

This tool aims at improving the resiliency of python services that might make
use of environment variables.

It requires human convention but is quite helpful at reducing potencial
for human error.

## Rationale

As codebases and number of contributors grow, there are certain moving
parts that become difficult to orchestrate.

For most of the configuration parts there are established tools and infrastructure that help in coordinating
so new needs and components by one team are reflected throughout the organization.

Environment variables are not, for the most part, in this category.  It is possible that their use began as local
by one or several teams and then grew to be shared and a requirement which must be managed by the ops team.

We aim with this set of tools and libraries at helping teams order their existing catalog of environment
variables and keep them up to date and properly documented going forward.

It is worth mentioning that, if your team is beginning on a project and there is a established disciplined 
culture of maintained human created metadata, there are other tools available. A good example is [EnvGuardian](
https://github.com/femitubosun/EnvGuardian
) which allows tracking of said variables albeit by hand.

## Features
* Create and update an environment variables catalog
* Perform checks of variables in code and missing from catalog.
* Scan environment and issue report of missing environment variables
* Invoke as a function pre-execution of entrypoint and fail early if variables are missing

## Usage

### As a library

#### Scanning
#### Guarding

### As a tool

#### Scanning
#### Checking catalog
#### Reporting on environment